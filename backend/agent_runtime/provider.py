"""Optional provider adapter for structured intent classification."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from backend.agent_runtime.plan import AgentPlan
from backend.config import Settings, get_settings
from backend.tools import summarize_customer_issue

ROUTER_INSTRUCTIONS = """
Classify requests for a fintech support application. Return one JSON object with
exactly: intent, transaction_id, user_id, needs_clarification, escalate, confidence.
Allowed intents: small_talk, account_summary, transaction_status,
transaction_history, refund, kyc, risk, complaint, policy, private_data,
prohibited_advice, general_support. IDs must match TXN plus letters/digits or U plus
digits; otherwise use null. Use account_summary for balance, account overview, or
profile-summary requests. Use transaction_history when the customer asks to see their
transactions without giving one transaction ID. Complaints, disputes, or human-agent
requests use complaint and escalate=true. Never invent an identifier. Use small_talk
for greetings, thanks, okay/got-it closings, casual social questions, or capability
questions. For small_talk, keep transaction_id and user_id null even if the
conversation history contains previous IDs, unless the latest user message clearly
asks to act on that ID.
""".strip()

RESPONSE_POLISH_INSTRUCTIONS = """
Rewrite a grounded fintech support response so it sounds warm, natural, and helpful.
Return exactly one JSON object with a single key: response.

Rules:
- Do not add facts, timelines, promises, approvals, refunds, balances, or policy details.
- Preserve transaction IDs, user IDs, ticket IDs, statuses, and risk labels.
- Keep refusals and safety boundaries intact.
- Do not claim that a human has acted unless the grounded response already says a ticket exists.
- Keep it concise: usually 1-4 short sentences.
- If the grounded response is already good, lightly improve tone only.
""".strip()

IDENTIFIER_PATTERN = re.compile(
    r"\b(?:TXN[A-Z0-9]+|U\d+|TCK-[A-Z0-9]+|\d{8,16})\b",
    re.IGNORECASE,
)
NUMBER_PATTERN = re.compile(r"(?<![A-Z])\b\d+(?:,\d{3})*(?:\.\d+)?\b", re.IGNORECASE)
FACT_TERMS = frozenset(
    {
        "active",
        "closed",
        "failed",
        "high",
        "low",
        "medium",
        "pending",
        "posted",
        "rejected",
        "success",
        "successful",
        "verified",
    }
)


class IntentProvider(Protocol):
    def route(self, message: str, history: list[dict]) -> AgentPlan | None: ...


class OpenAICompatibleProvider:
    """Call an OpenAI-compatible endpoint and validate every result locally."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _connection_options(self) -> tuple[str, str | None] | None:
        """Return provider credentials or disable provider routing.

        ``LLM_PROVIDER=local`` means deterministic local routing with no model call.
        ``LLM_PROVIDER=ollama`` uses Ollama's local OpenAI-compatible endpoint and
        accepts a dummy API key because local Ollama usually does not require one.
        """
        provider = self.settings.llm_provider
        if provider == "local":
            return None
        if provider == "ollama":
            base_url = self.settings.llm_base_url or "http://127.0.0.1:11434/v1"
            return self.settings.llm_api_key or "ollama", base_url
        if not self.settings.llm_api_key:
            return None
        if provider == "deepseek":
            base_url = self.settings.llm_base_url or "https://api.deepseek.com"
            return self.settings.llm_api_key, base_url
        return self.settings.llm_api_key, self.settings.llm_base_url

    def route(self, message: str, history: list[dict]) -> AgentPlan | None:
        connection_options = self._connection_options()
        if connection_options is None:
            return None
        try:
            from openai import OpenAI

            api_key, base_url = connection_options
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=1,
            )
            messages: Any = [{"role": "system", "content": ROUTER_INSTRUCTIONS}]
            for item in history[-6:]:
                role = item.get("role")
                if role in {"user", "assistant"}:
                    messages.append(
                        {
                            "role": role,
                            "content": summarize_customer_issue(str(item.get("content", ""))),
                        }
                    )
            messages.append({"role": "user", "content": summarize_customer_issue(message)})
            response_format: Any = {"type": "json_object"}
            completion = client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                response_format=response_format,
            )
            content = completion.choices[0].message.content
            if not content:
                return None
            return AgentPlan.model_validate(json.loads(content))
        except Exception:
            return None

    @staticmethod
    def _identifiers(text: str) -> set[str]:
        return {match.group(0).upper() for match in IDENTIFIER_PATTERN.finditer(text)}

    @staticmethod
    def _facts(text: str) -> tuple[set[str], set[str]]:
        numbers = {match.group(0) for match in NUMBER_PATTERN.finditer(text)}
        words = set(re.findall(r"[a-z]+", text.lower()))
        return numbers, words & FACT_TERMS

    def _safe_polished_response(self, grounded_response: str, candidate: str) -> str | None:
        cleaned = candidate.strip()
        if not cleaned or len(cleaned) > 1400:
            return None

        original_ids = self._identifiers(grounded_response)
        candidate_ids = self._identifiers(cleaned)
        if not original_ids <= candidate_ids:
            return None
        if not candidate_ids <= original_ids:
            return None

        if self._facts(grounded_response) != self._facts(cleaned):
            return None

        lowered_grounded = grounded_response.lower()
        lowered_candidate = cleaned.lower()
        refusal_terms = ("cannot", "can't", "could not", "couldn’t", "do not want to guess")
        if any(term in lowered_grounded for term in refusal_terms) and not any(
            term in lowered_candidate for term in refusal_terms
        ):
            return None

        return cleaned

    def polish_response(
        self,
        *,
        message: str,
        intent: str,
        grounded_response: str,
        tools_used: list[str],
        sources: list[str],
    ) -> str | None:
        """Use the provider to make a grounded response sound more natural."""
        if not self.settings.llm_polish_responses:
            return None
        connection_options = self._connection_options()
        if connection_options is None:
            return None
        try:
            from openai import OpenAI

            api_key, base_url = connection_options
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=1,
            )
            payload = {
                "user_message": summarize_customer_issue(message),
                "intent": intent,
                "grounded_response": grounded_response,
                "tools_used": tools_used,
                "sources": sources,
            }
            completion = client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": RESPONSE_POLISH_INSTRUCTIONS},
                    {"role": "user", "content": json.dumps(payload)},
                ],
                response_format={"type": "json_object"},
            )
            content = completion.choices[0].message.content
            if not content:
                return None
            candidate = json.loads(content).get("response")
            if not isinstance(candidate, str):
                return None
            return self._safe_polished_response(grounded_response, candidate)
        except Exception:
            return None
