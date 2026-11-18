"""Transaction selection and case handling for signed-in portal Help."""

import hashlib
import re
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.conversations import add_audit_log
from backend.models import SupportCaseTransaction, Ticket
from backend.schemas import ChatRequest
from backend.security import Principal
from backend.tools import get_transaction_status, list_user_transactions

_TRANSACTION_REFERENCE = re.compile(
    r"\b(?:FAIL[0-9A-F]{16}|TXN(?:[0-9A-F]{16}[SR]?|[0-9]{4}))\b", re.IGNORECASE
)

_SEND_REQUEST = re.compile(
    r"^(?:(?:hi|hey|hello)[, !]+)?"
    r"(?:(?:can|could|would|will) you |(?:can|could|how do) i |"
    r"i (?:want|need|would like) to |i['’]d like to )?"
    r"(?:please )?(?:(?:transfer|send|move)\s+(?:₹|rs\.?\s*\d|\d|money\b|"
    r"(?:\w+\s+){1,3}(?:₹|rs\.?\s*\d|\d))|"
    r"(?:send|transfer) to [\w][\w'’-]*(?: [\w'’-]+){0,2}[.!?]*$)"
)
_NAME_CORRECTION = re.compile(
    r"\b(?:change|correct|update|amend|fix|edit|rename)\b"
    r"[^.!?]*\b(?:holder(?:['’]s)? name|name on my account|account name|my name)\b"
)
_NONRECEIPT = re.compile(
    r"\b(?:didn['’]t|did not|hasn['’]t|has not) (?:get|receive) "
    r"(?:the |my |any )?(?:money|payment|transfer)\b"
)
_STATEMENT_REQUEST = re.compile(
    r"^(?:(?:can|could|would) (?:i|you) |how (?:can|do) i |where (?:can|do) i |please )?"
    r"(?:download|get|export|show|send|give)\b[^.!?]*\bstatements?\b"
    r"|^(?:(?:my|bank|account) )?statements?[.!?]*$"
)

_CASE_REQUEST = re.compile(
    r"\b(?:(?:open|create|raise|file) (?:a |an |the |another )?"
    r"(?:support )?(?:case|ticket|complaint)"
    r"|(?:talk|speak|connect) (?:to|with) (?:support|a person|someone|a human|an agent)"
    r"|(?:i (?:want|need) to )?make (?:a |an )?complaint|escalate (?:this|my complaint)"
    r"|dispute this)\b",
    re.IGNORECASE,
)
_SHORT_FAILURE = re.compile(
    r"\b(?:transactions?|transfers?|payments?|withdrawals?) (?:that )?"
    r"(?:failed|declined|didn['’]t go through|did not go through)\b"
)
_DISPUTE = re.compile(
    r"\b(?:(?:charged|debited)(?: me| my (?:account|card))? twice|"
    r"duplicate (?:debit|charge|payment)|double[- ]charged)\b"
    r"|\b(?:atm|cash machine)\b.*\b(?:no cash|(?:didn['’]t|did not) dispense|"
    r"never (?:gave|dispensed))\b"
    r"|\b(?:money (?:is |has gone |went )?missing|missing money|"
    r"(?:don['’]t|do not) recogni[sz]e (?:this|that|a) (?:charge|payment|transaction))\b"
)
_CASE_DETAILS = re.compile(r"\bTCK-[A-Z0-9]+\b", re.IGNORECASE)
_CASE_TOPIC = re.compile(r"\b(?:case|ticket|complaint)s?\b")
_TRANSACTION_TOPIC = re.compile(r"\b(transaction|transfer|payment|withdrawal)s?\b")
_OTHER_STATUS_TOPIC = re.compile(r"\b(?:kyc|verification|identity|account opening)\b")
_CASE_STATUS = re.compile(
    r"\b(?:update|updates|status|progress|resolved|closed|open|heard back|looked at|"
    r"looking into|working on|happening|happened|what (?:was|is) .+ about)\b"
)
_STATUS_FOLLOWUP = re.compile(
    r"^(?:can you tell me )?(?:(?:any|got any) (?:news|updates?|progress)|"
    r"where (?:do we stand|are we at|(?:is|are) (?:this|it|we) up to|(?:this|it) is up to)|"
    r"what(?:['’]?s| is) (?:the )?(?:update|status)|"
    r"has there been any (?:news|updates?|progress))\b"
)
_CASE_FOLLOWUP = re.compile(
    r"^(?:"
    r"(?:is|has) (?:it|this|that) (?:still open|been resolved|closed|been closed)|"
    r"(?:did|has) (?:anyone|someone) (?:look|looked|respond|responded)|"
    r"(?:is|has) (?:it|this|that) (?:being reviewed|been looked at)|"
    r"what (?:was|is) (?:it|this|that) (?:for|about))\b"
)
_ACTIVE_CASES = re.compile(
    r"\b(?:active|open|unresolved) (?:support )?(?:case|ticket|complaint)s?\b"
)
_CASE_LIST = re.compile(
    r"^(?:cases?|tickets?|complaints?)$|"
    r"\b(?:my|any|open|existing|previous) (?:support )?(?:cases|tickets|complaints)\b|"
    r"\b(?:show|list|find|see|track) (?:me )?(?:the |my |all )?"
    r"(?:support )?(?:cases?|tickets?|complaints?)\b"
)
_PRIVACY_QUESTION = re.compile(
    r"\b(?:who|can|does|do)\b.*\b(?:see|access|read|view|share|private|privacy)\b"
    r".*\b(?:my|account)\b"
)
_CARD_ISSUE = re.compile(
    r"\b(?:card payment|debit card|credit card|card)\b.*\b(?:declined|failed|rejected)\b"
)
_FAILED_LIST = re.compile(
    r"\b(?:failed|declined) (?:transactions?|transcations?|transfers?|payments?)\b"
)
_DRAFT_KEYS = ("case_description", "case_awaiting_issue", "case_offer", "case_offer_transaction")


def _clear_case_draft(context: dict) -> None:
    for key in _DRAFT_KEYS:
        context.pop(key, None)


def _meaningful_issue(text: str) -> bool:
    words = re.findall(r"\b[\w’']+\b", text.casefold())
    return (
        len(words) >= 4
        or bool(_SHORT_FAILURE.search(text.casefold()) or _DISPUTE.search(text.casefold()))
        or bool(re.search(r"\bmissing (?:payment|transfer)\b", text, re.I))
    ) and not (
        _CASE_REQUEST.fullmatch(text.strip(" ?."))
        or re.fullmatch(
            r"(?:yes|okay|ok|sure|thanks|thank you|please|hi|hello|help)(?:[ ,.?!]+.*)?", text, re.I
        )
    )


def _issue_from_request(message: str, request: re.Match[str]) -> str:
    suffix = _TRANSACTION_REFERENCE.sub("", message[request.end() :]).strip()
    match = re.match(r"(?:[:—-]\s*|(?:for|because|about|to)\s+)", suffix, re.I)
    return suffix[match.end() :].strip() if match else ""


def _prepare_case(
    db: Session,
    user_id: str,
    context: dict,
    issue: str = "",
    *,
    link_selected: bool = True,
    introduction: str = "",
) -> dict:
    selected = context.get("selected_transaction") if link_selected else None
    if selected:
        existing = _case_list(db, user_id, reference=selected["reference"])
        if existing:
            return _existing_case_reply(context, existing[0])
    context["case_offer_transaction"] = selected
    if not _meaningful_issue(issue):
        context["case_awaiting_issue"] = True
        context.pop("case_offer", None)
        context.pop("case_description", None)
        return _reply(
            "I can help you open a support case. What happened?",
            selected_transaction=selected,
        )
    context.pop("case_awaiting_issue", None)
    context["case_description"] = " ".join(issue.split())
    context["case_offer"] = True
    return _reply(
        introduction + "Review the summary below, then confirm if you’d like me to open the case.",
        case_offer=True,
        case_summary=context["case_description"],
        selected_transaction=selected,
    )


def _saved_summary(description: str) -> str | None:
    request = _CASE_REQUEST.search(description)
    if request and not _issue_from_request(description, request):
        return None
    return description.strip() or None


def _transaction_card(transaction: dict) -> dict:
    return {
        "reference": str(transaction.get("transaction_id") or transaction.get("reference_number")),
        "amount": str(transaction.get("amount") or "0"),
        "status": str(transaction.get("status") or "unknown"),
        "type": str(transaction.get("transaction_type") or "transaction"),
        "failure_reason": transaction.get("failure_reason"),
        "timestamp": transaction.get("timestamp"),
    }


def _case_list(
    db: Session, user_id: str, *, reference: str | None = None, active_only: bool = False
) -> list[dict]:
    query = (
        select(Ticket, SupportCaseTransaction.transaction_reference)
        .outerjoin(SupportCaseTransaction, SupportCaseTransaction.ticket_id == Ticket.ticket_id)
        .where(Ticket.user_id == user_id)
        .order_by(Ticket.created_at.desc())
    )
    if reference:
        query = query.where(SupportCaseTransaction.transaction_reference == reference)
    if active_only:
        query = query.where(Ticket.status.in_(("open", "in_progress")))
    return [
        {
            "ticket_id": ticket.ticket_id,
            "status": ticket.status,
            "issue_type": ticket.issue_type,
            "transaction_reference": reference,
            "summary": _saved_summary(ticket.description),
        }
        for ticket, reference in db.execute(query)
    ]


def _existing_case_reply(context: dict, case: dict) -> dict:
    _clear_case_draft(context)
    context.pop("case_list_active", None)
    context["selected_case_id"] = case["ticket_id"]
    context["case_ticket_id"] = case["ticket_id"]
    context["case_ticket_ref"] = case["transaction_reference"]
    return _reply(
        "This transaction already has a support case. "
        f"Case {case['ticket_id']} is {case['status']}.",
        ticket_id=case["ticket_id"],
        cases=[case],
        tools_used=["list_owned_cases"],
    )


def answer_help(
    payload: ChatRequest, principal: Principal, db: Session, conversation_id: str, context: dict
) -> dict | None:
    """Handle the portal's transaction and case workflow before general routing."""
    user_id = principal.user_id
    assert user_id is not None
    lowered = payload.message.strip().casefold()
    action = payload.action
    if action == "clear_transaction":
        context.pop("selected_transaction", None)
        context["transaction_selection_cleared"] = True
        if context.get("case_offer_transaction"):
            _clear_case_draft(context)
        if context.get("case_ticket_ref"):
            context.pop("case_ticket_id", None)
            context.pop("case_ticket_ref", None)
        return _reply(
            "Transaction selection cleared.",
            case_offer=bool(context.get("case_offer")),
        )
    if action == "confirm_case":
        return _confirm_case(payload, principal, db, conversation_id, context, user_id)
    if any(
        phrase in lowered
        for phrase in ("cancel it", "cancel this", "cancel the case", "never mind")
    ):
        if context.get("case_offer") or context.get("case_awaiting_issue"):
            _clear_case_draft(context)
            return _reply(
                "I’ve cancelled the draft. You can start a new case whenever you’re ready."
            )

    if action is None and _NAME_CORRECTION.search(lowered):
        return _reply(
            "Contact support to request an account holder name correction. "
            "A bank administrator can review and correct the name."
        )

    if action is None and _STATEMENT_REQUEST.search(lowered):
        answer = "You can download your statement from Overview → Download statement CSV."
        if any(
            period in lowered for period in ("last month", "date range", "this month", "last year")
        ):
            answer += " The CSV includes all transactions for the selected account."
        return _reply(answer, next_action="download_statement")

    if action is None and _SEND_REQUEST.search(lowered):
        return _reply(
            "To send money, open Transfer and review the recipient and amount before confirming.",
            next_action="open_transfer",
        )

    case_request = _CASE_REQUEST.search(payload.message)
    case_id_match = _CASE_DETAILS.search(payload.message)
    selected_case_id = context.get("selected_case_id")
    message_match = _TRANSACTION_REFERENCE.search(payload.message)
    message_ref = message_match.group(0) if message_match else None
    case_topic = _CASE_TOPIC.search(lowered)
    transaction_topic = _TRANSACTION_TOPIC.search(lowered)
    status_question = bool(
        _STATUS_FOLLOWUP.search(lowered) and not _OTHER_STATUS_TOPIC.search(lowered)
    )
    transaction_status = bool(status_question and transaction_topic and not case_topic)
    active_cases = bool(_ACTIVE_CASES.search(lowered))
    wants_details = any(
        phrase in lowered
        for phrase in (
            "case is for",
            "case for",
            "case about",
            "case is about",
            "ticket for",
            "ticket about",
        )
    )
    wants_details = (
        wants_details
        or (
            bool(case_topic and _CASE_STATUS.search(lowered))
            and not (active_cases or _CASE_LIST.search(lowered))
        )
        or bool(
            (selected_case_id or context.get("case_list_active"))
            and not (message_ref or action or transaction_status)
            and (status_question or _CASE_FOLLOWUP.search(lowered))
        )
    )
    if (
        action == "list_cases"
        or case_id_match
        or (
            action is None
            and (active_cases or not case_request and (wants_details or _CASE_LIST.search(lowered)))
        )
    ):
        cases = _case_list(db, user_id, active_only=active_cases and not case_id_match)
        if action != "list_cases" and (case_id_match or (wants_details and not active_cases)):
            target = case_id_match.group().upper() if case_id_match else selected_case_id
            matches = [case for case in cases if case["ticket_id"] == target]
            if not target and len(cases) == 1:
                matches = cases
            if matches:
                case = matches[0]
                context["selected_case_id"] = case["ticket_id"]
                context.pop("case_list_active", None)
                summary = case["summary"] or "No issue details were recorded."
                return _reply(
                    f"Case {case['ticket_id']} is {case['status']}. {summary}",
                    cases=matches,
                    tools_used=["list_owned_cases"],
                )
            if target or not cases:
                if case_id_match:
                    context.pop("selected_case_id", None)
                return _reply(
                    "I couldn’t find that case under your account.", tools_used=["list_owned_cases"]
                )
            context["case_list_active"] = True
            return _reply(
                "Which case would you like me to explain?",
                cases=cases,
                tools_used=["list_owned_cases"],
            )
        context.pop("selected_case_id", None)
        context["case_list_active"] = bool(cases)
        if active_cases:
            return _reply(
                "Here are your active support cases."
                if cases
                else "You have no active support cases.",
                cases=cases,
                tools_used=["list_owned_cases"],
            )
        answer = (
            "Here are your support cases."
            if cases
            else "I couldn’t find any support cases for your account."
        )
        return _reply(answer, cases=cases, tools_used=["list_owned_cases"])

    if (
        _PRIVACY_QUESTION.search(lowered)
        and not re.search(r"\b(?:another|someone else|other customer)\b", lowered)
        and ("my account" in lowered or "my data" in lowered or "my information" in lowered)
    ):
        return _reply(
            "Help uses your signed-in account to look up your banking records when you ask. "
            "I can’t verify who at the bank has accessed your information from this chat. "
            "If you’re concerned about access, you can open a support case."
        )

    if _CARD_ISSUE.search(lowered) or re.search(
        r"\b(?:declined|rejected) (?:my |the )?card\b", lowered
    ):
        return _prepare_case(
            db,
            user_id,
            context,
            payload.message,
            link_selected=False,
            introduction="I can review CoreBank transfers here. Card authorization details aren’t "
            "available in this demo, but you can record the issue in a support case. ",
        )

    if re.fullmatch(r"(?:hello|hi|hey)[, !.]+(?:can|could) you help me[?!. ]*", lowered):
        return _reply("Of course. What can I help you with today?")

    typed_ref = message_ref or (
        payload.transaction_reference if action == "select_transaction" else None
    )
    failed_list = bool(_FAILED_LIST.search(lowered))
    vague_withdrawal = any(
        term in lowered
        for term in ("last withdrawal declined", "withdrawal declined", "withdrawal failed")
    )
    vague_recipient = bool(_NONRECEIPT.search(lowered)) or any(
        term in lowered
        for term in (
            "friend didn't receive",
            "friend did not receive",
            "didn't receive it",
            "hasn't received",
            "has not received",
            "never got",
            "not received",
            "still waiting for the money",
            "happening with my transfer to",
            "paise nahi mile",
            "paise nahin mile",
            "abhi tak nahi mile",
        )
    )
    vague_transaction = any(
        term in lowered
        for term in (
            "explain a transaction",
            "explain this transaction",
            "help with a failed transaction",
            "failed transaction",
            "why did that one fail",
            "why did it fail",
        )
    )
    selected_context = context.get("selected_transaction")
    contextual_transaction_followup = bool(
        selected_context
        and (
            vague_recipient
            or status_question
            or any(
                term in lowered
                for term in (
                    "why did that one fail",
                    "why did it fail",
                    "why was it declined",
                    "what happened to it",
                    "already selected the transaction",
                    "already chose the transaction",
                    "selected this transaction",
                    "did it go through",
                    "has it gone through",
                    "money back",
                    "refund",
                    "debited",
                    "deducted",
                    "reversed",
                )
            )
        )
    )
    # A question that names a different kind of transaction needs fresh choices.
    transaction_kind = (
        transaction_topic.group(1) if transaction_status and transaction_topic else ""
    )
    kind_prefix = {"transfer": "transfer", "withdrawal": "withdraw"}.get(transaction_kind)
    if kind_prefix and selected_context:
        contextual_transaction_followup = (
            contextual_transaction_followup and kind_prefix in selected_context["type"].casefold()
        )
    if status_question and not (
        case_topic
        or transaction_topic
        or selected_context
        or typed_ref
        or action
        or case_request
        or context.get("case_awaiting_issue")
    ):
        return _reply("Are you asking about a transaction or support case?")
    if contextual_transaction_followup and selected_context and not typed_ref:
        typed_ref = selected_context.get("reference")
    dispute = _DISPUTE.search(lowered)
    if dispute and not message_ref and action is None:
        issue = (
            _issue_from_request(payload.message, case_request) if case_request else payload.message
        )
        return _prepare_case(
            db,
            user_id,
            context,
            issue or payload.message,
            link_selected=False,
            introduction="I can help you report this for review. ",
        )

    if (
        context.get("case_awaiting_issue")
        and action is None
        and not case_request
        and not message_ref
        and not any(
            term in lowered
            for term in (
                "my balance",
                "my account balance",
                "my kyc",
                "my transactions",
                "what can you do",
                "what all can you do",
                "how much money do i have",
            )
        )
    ):
        if not _meaningful_issue(payload.message):
            return _reply(
                "Tell me a little about the issue. For example, “My transaction failed” "
                "or “I was charged twice.”",
                selected_transaction=selected_context,
            )
        return _prepare_case(db, user_id, context, payload.message)

    if action == "select_transaction" or message_ref or contextual_transaction_followup:
        if not typed_ref:
            return _reply(
                "Choose a transaction from your Activity list so I can check it.",
            )
        transaction = get_transaction_status(typed_ref, user_id)
        if transaction.get("error"):
            return _reply(
                "I couldn’t reach CoreBank to check that transaction. Please try again.",
                tools_used=["get_transaction_status"],
            )
        if not transaction.get("found") or transaction.get("user_id") != user_id:
            if action == "select_transaction" or message_ref:
                context.clear()
            return _reply(
                "I couldn’t find that transaction in your account. "
                "Choose one from your Activity list.",
                tools_used=["get_transaction_status"],
            )
        card = _transaction_card(transaction)
        if action == "select_transaction" or message_ref or transaction_status:
            context.pop("selected_case_id", None)
            context.pop("case_list_active", None)
        context.update(selected_transaction=card)
        offered = context.get("case_offer_transaction")
        if offered and offered["reference"] != card["reference"]:
            _clear_case_draft(context)
        if context.get("case_ticket_ref") != card["reference"]:
            context.pop("case_ticket_id", None)
            context.pop("case_ticket_ref", None)
        if case_request or dispute or context.get("case_awaiting_issue") and message_ref:
            issue = (
                _issue_from_request(payload.message, case_request)
                if case_request
                else payload.message
            )
            return _prepare_case(db, user_id, context, issue)

        answer = _explain_transaction(card, from_corebank=transaction.get("source") == "corebank")
        if vague_recipient and card["status"] == "posted":
            answer = (
                f"CoreBank shows transfer {card['reference']} as posted. "
                "If the recipient still cannot locate it, open a support case so we can review it."
            )
        return _reply(
            answer,
            selected_transaction=card,
            tools_used=["get_transaction_status"],
        )

    if case_request:
        return _prepare_case(
            db, user_id, context, _issue_from_request(payload.message, case_request)
        )

    if (
        failed_list
        or vague_withdrawal
        or vague_recipient
        or vague_transaction
        or transaction_status
        or _SHORT_FAILURE.search(lowered)
    ):
        result = list_user_transactions(user_id, limit=50)
        if result.get("error"):
            return _reply(
                "I couldn’t load your recent transactions right now. Please try again.",
                tools_used=["list_user_transactions"],
            )
        candidates = result.get("transactions", [])
        if transaction_status:
            context.pop("selected_case_id", None)
            context.pop("case_list_active", None)
            if kind_prefix:
                candidates = [
                    t for t in candidates if kind_prefix in t.get("transaction_type", "").casefold()
                ]
        elif vague_withdrawal:
            candidates = [
                t
                for t in candidates
                if "withdraw" in t.get("transaction_type", "").casefold()
                and t.get("status") == "failed"
            ]
        elif failed_list or _SHORT_FAILURE.search(lowered):
            candidates = [t for t in candidates if t.get("status") == "failed"]
        elif vague_recipient:
            candidates = [
                t
                for t in candidates
                if any(
                    x in str(t.get("transaction_type", "")).casefold()
                    for x in ("transfer", "payment")
                )
                and t.get("transaction_type") != "transfer_received"
            ]
        elif vague_transaction:
            candidates = [
                t for t in candidates if str(t.get("status", "")).casefold() == "failed"
            ] or candidates
        options = [_transaction_card(t) for t in candidates[:5]]
        if failed_list or vague_withdrawal:
            answer = (
                "Here are your recent failed transactions. Select one to see what happened."
                if options
                else "You have no recent failed transactions."
            )
        else:
            answer = (
                "Which transaction do you mean? Choose one below."
                if options
                else "I couldn’t find a recent match. Choose a transaction from Activity "
                "or share its reference."
            )
        return _reply(
            answer,
            transaction_options=options,
            tools_used=["list_user_transactions"],
        )

    return None


def _confirm_case(
    payload: ChatRequest,
    principal: Principal,
    db: Session,
    conversation_id: str,
    context: dict,
    user_id: str,
) -> dict:
    offered = context.get("case_offer_transaction")
    offered_ref = offered.get("reference") if offered else None
    requested_ref = payload.transaction_reference or offered_ref
    if offered_ref and offered_ref == requested_ref:
        existing = _case_list(db, user_id, reference=offered_ref)
        if existing:
            return _existing_case_reply(context, existing[0])
    if context.get("case_ticket_id") and context.get("case_ticket_ref") == requested_ref:
        ticket = db.scalar(
            select(Ticket).where(
                Ticket.ticket_id == context["case_ticket_id"], Ticket.user_id == user_id
            )
        )
        if ticket:
            return _reply(
                f"Case {ticket.ticket_id} is {ticket.status}.",
                ticket_id=ticket.ticket_id,
            )
    desc = context.get("case_description", "")
    if not context.get("case_offer") or requested_ref != offered_ref or not _meaningful_issue(desc):
        return _reply(
            "I don’t have a matching case ready to confirm. Tell me what happened first.",
        )

    issue_type = "failed_transaction" if offered else "general_support"
    stable_key = offered_ref or conversation_id
    ticket_id = "TCK-" + hashlib.sha256(f"{user_id}:{stable_key}".encode()).hexdigest()[:24].upper()
    dialect = db.get_bind().dialect.name
    insert_fn = (
        pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    )
    values = {
        "ticket_id": ticket_id,
        "user_id": user_id,
        "issue_type": issue_type,
        "description": desc,
        "priority": "medium",
        "status": "open",
    }
    ticket_was_new = False
    if insert_fn:
        inserted_ticket_id = db.scalar(
            insert_fn(Ticket)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["ticket_id"])
            .returning(Ticket.ticket_id)
        )
        ticket_was_new = inserted_ticket_id is not None
    elif db.scalar(select(Ticket).where(Ticket.ticket_id == ticket_id)) is None:
        db.add(Ticket(**values))
        db.flush()
        ticket_was_new = True
    if offered_ref and insert_fn:
        db.execute(
            insert_fn(SupportCaseTransaction)
            .values(ticket_id=ticket_id, transaction_reference=offered_ref)
            .on_conflict_do_nothing(index_elements=["transaction_reference"])
        )
    elif (
        offered_ref
        and db.scalar(
            select(SupportCaseTransaction).where(
                SupportCaseTransaction.transaction_reference == offered_ref
            )
        )
        is None
    ):
        db.add(SupportCaseTransaction(ticket_id=ticket_id, transaction_reference=offered_ref))
    owned_ticket = db.scalar(
        select(Ticket).where(Ticket.ticket_id == ticket_id, Ticket.user_id == user_id)
    )
    if owned_ticket is None:
        raise RuntimeError("Unable to verify ownership of the saved support case")
    if offered_ref and not ticket_was_new:
        existing = _case_list(db, user_id, reference=offered_ref)
        if existing:
            return _existing_case_reply(context, existing[0])
    if ticket_was_new:
        add_audit_log(
            db,
            actor_subject=principal.subject,
            action="ticket.created",
            resource_type="ticket",
            resource_id=ticket_id,
        )
    context.pop("case_list_active", None)
    context["selected_case_id"] = ticket_id
    context["case_ticket_id"] = ticket_id
    context["case_ticket_ref"] = offered_ref
    context["case_offer"] = False
    return _reply(
        f"Case {ticket_id} is {owned_ticket.status}."
        + (f" Linked transaction: {offered_ref}." if offered_ref else ""),
        ticket_id=ticket_id,
        tools_used=["create_support_ticket"],
    )


def _explain_transaction(card: dict, *, from_corebank: bool) -> str:
    amount = f"₹{Decimal(card['amount']):,.2f}"
    reference = card["reference"]
    status = card["status"]
    if status.casefold() != "failed":
        return f"{reference} is marked {status} for {amount}. What would you like me to check?"

    reason = card["failure_reason"]
    details = f" CoreBank recorded: {reason}." if reason else ""
    if from_corebank and "withdraw" in card["type"].casefold() and reason == "Insufficient balance":
        return (
            f"{reference} is a failed withdrawal for {amount}.{details} "
            "The withdrawal was not debited, so there is no refund to track."
        )
    return (
        f"{reference} is marked failed for {amount}.{details} "
        "This record does not show whether a debit or refund occurred."
    )


def _reply(
    answer: str,
    *,
    selected_transaction: dict | None = None,
    transaction_options: list[dict] | None = None,
    cases: list[dict] | None = None,
    case_offer: bool = False,
    ticket_id: str | None = None,
    tools_used: list[str] | None = None,
    case_summary: str | None = None,
    next_action: str | None = None,
) -> dict:
    return {
        "response": answer,
        "tools_used": tools_used or [],
        "ticket_id": ticket_id,
        "escalated": bool(ticket_id),
        "sources": [],
        "selected_transaction": selected_transaction,
        "transaction_options": transaction_options or [],
        "case_offer": case_offer,
        "cases": cases or [],
        "case_summary": case_summary,
        "next_action": next_action,
    }
