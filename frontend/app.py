"""Streamlit customer chatbot and authenticated operations dashboard."""

import os

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("FINTECH_API_URL", "http://127.0.0.1:8000").rstrip("/")
BANKING_DATA_SOURCE = os.getenv("BANKING_DATA_SOURCE", "local")
REQUEST_TIMEOUT = 15
STATIC_ACCESS_TOKEN = os.getenv("FINTECH_ACCESS_TOKEN", "").strip()
DEV_AUTH = os.getenv("FINTECH_DEV_AUTH", "true").lower() in {"1", "true", "yes"}

st.set_page_config(page_title="Fintech AI Support Agent", page_icon="💳", layout="centered")
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 760px !important;
    }
    [data-testid="stMetric"] {background: #f7f9fc; border: 1px solid #e5eaf2;
                              padding: 1rem; border-radius: .75rem;}
    .subtle {color: #667085; margin-top: -.6rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3000, show_spinner=False)
def development_token(user_id: str | None, role: str) -> str:
    response = requests.post(
        f"{API_URL}/auth/dev-token",
        json={"user_id": user_id, "role": role},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def access_token(user_id: str | None, role: str) -> str:
    if STATIC_ACCESS_TOKEN:
        return STATIC_ACCESS_TOKEN
    if DEV_AUTH:
        return development_token(user_id, role)
    return ""


def auth_headers(user_id: str | None, role: str) -> dict[str, str]:
    token = access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"} if token else {}


def api_get(path: str, *, user_id: str | None = None, role: str = "customer"):
    response = requests.get(
        f"{API_URL}{path}",
        headers=auth_headers(user_id, role),
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def send_chat(message: str, user_id: str) -> dict:
    response = requests.post(
        f"{API_URL}/chat",
        headers=auth_headers(user_id, "customer"),
        json={
            "message": message,
            "conversation_id": st.session_state.get("conversation_id"),
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def reset_identity_state(user_id: str) -> None:
    if st.session_state.get("active_user_id") == user_id:
        return
    st.session_state.active_user_id = user_id
    st.session_state.conversation_id = None
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": f"Signed in as {user_id}. How can I help with your account?",
            "tools_used": [],
        }
    ]


def show_chatbot(user_id: str) -> None:
    reset_identity_state(user_id)
    st.title("Fintech AI Support Agent")
    st.markdown(
        '<p class="subtle">Authenticated transaction help, policy answers, '
        "and human escalation.</p>",
        unsafe_allow_html=True,
    )
    st.caption(f"Customer identity: {user_id}")

    examples_by_user = {
        "U001": ["What is my account balance?", "Show my transactions", "Check my KYC"],
        "U002": [
            "What is my account balance?",
            "Show my transactions",
            "Review account activity risk",
        ],
        "U003": [
            "What is my account balance?",
            "Show my transactions",
            "Review account activity risk",
        ],
    }
    st.caption("Try an example")
    examples = examples_by_user[user_id]
    columns = st.columns(2)
    selected_example = None
    for index, example in enumerate(examples):
        column = columns[index % len(columns)]
        if column.button(example, use_container_width=True):
            selected_example = example

    for item in st.session_state.messages:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
            if item.get("sources"):
                st.caption("Sources: " + ", ".join(item["sources"]))
            if item.get("tools_used"):
                with st.expander("Agent activity"):
                    st.write("Tools used: " + ", ".join(item["tools_used"]))
                    if item.get("ticket_id"):
                        st.success(f"Escalated as ticket {item['ticket_id']}")

    prompt = selected_example or st.chat_input(
        "Ask about a transaction, refund, KYC status, policy, or complaint..."
    )
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Checking authorization, records, and approved policies..."):
            try:
                result = send_chat(prompt, user_id)
                st.session_state.conversation_id = result["conversation_id"]
                st.markdown(result["response"])
                if result.get("sources"):
                    st.caption("Sources: " + ", ".join(result["sources"]))
                if result.get("tools_used"):
                    with st.expander("Agent activity"):
                        st.write("Tools used: " + ", ".join(result["tools_used"]))
                        if result.get("ticket_id"):
                            st.success(f"Escalated as ticket {result['ticket_id']}")
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": result["response"],
                        "tools_used": result.get("tools_used", []),
                        "ticket_id": result.get("ticket_id"),
                        "sources": result.get("sources", []),
                    }
                )
            except requests.RequestException as exc:
                detail = "The authenticated support API could not complete this request."
                if getattr(exc, "response", None) is not None:
                    try:
                        detail = exc.response.json().get("detail", detail)
                    except ValueError:
                        pass
                st.error(detail)
                st.session_state.messages.append(
                    {"role": "assistant", "content": detail, "tools_used": []}
                )


def show_admin_dashboard() -> None:
    title_col, refresh_col = st.columns([5, 1])
    title_col.title("Operations Dashboard")
    title_col.markdown(
        '<p class="subtle">Authorized support demand, activity-risk review, '
        "and audit activity.</p>",
        unsafe_allow_html=True,
    )
    refresh_col.write("")
    refresh_col.write("")
    refresh_col.button("Refresh", use_container_width=True)

    try:
        summary = api_get("/admin/summary", role="admin")
        tickets = api_get("/admin/tickets", role="admin")
        risks = api_get("/admin/high-risk-transactions", role="admin")
        audits = api_get("/admin/audit", role="admin")
    except requests.RequestException:
        st.error(f"Could not authenticate with the FastAPI backend at {API_URL}.")
        return

    metric_columns = st.columns(4)
    metric_columns[0].metric("Total transactions", summary["total_transactions"])
    metric_columns[1].metric("Failed transactions", summary["failed_transactions"])
    metric_columns[2].metric("Open tickets", summary["open_tickets"])
    metric_columns[3].metric("High-risk local transactions", summary["high_risk_transactions"])

    st.subheader("Support tickets")
    if tickets:
        ticket_frame = pd.DataFrame(tickets)
        ticket_frame["created_at"] = pd.to_datetime(ticket_frame["created_at"]).dt.strftime(
            "%Y-%m-%d %H:%M"
        )
        st.dataframe(ticket_frame, use_container_width=True, hide_index=True)
    else:
        st.info("No tickets have been created yet.")

    st.subheader("High-risk local transactions")
    if risks:
        risk_frame = pd.DataFrame(risks)
        risk_frame["risk_reasons"] = risk_frame["risk_reasons"].apply("; ".join)
        st.dataframe(risk_frame, use_container_width=True, hide_index=True)
    else:
        st.success("No high-risk transactions currently require review.")

    with st.expander("Recent audit activity"):
        if audits:
            st.dataframe(pd.DataFrame(audits), use_container_width=True, hide_index=True)
        else:
            st.info("No audit events have been recorded yet.")


st.sidebar.title("Fintech Agent")
page = st.sidebar.radio("Navigation", ["Customer Chatbot", "Admin Dashboard"])
customer_id = st.sidebar.selectbox("Demo customer", ["U001", "U002", "U003"], index=1)
st.sidebar.divider()
st.sidebar.caption(f"API: {API_URL}")
st.sidebar.caption(f"Banking data: {BANKING_DATA_SOURCE}")
st.sidebar.caption("Development tokens are local-only." if DEV_AUTH else "External JWT mode")

if page == "Customer Chatbot":
    show_chatbot(customer_id)
else:
    show_admin_dashboard()
