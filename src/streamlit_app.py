from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from dotenv import load_dotenv

from src.main import RegBot
from src.regbot.compliance import chat_followup_policy_qa

st.set_page_config(page_title="GA4GH-RegBot", layout="wide")
load_dotenv()

st.title("GA4GH-RegBot")
st.caption(
    "Prototype assistant: ingest GA4GH-style policy excerpts, retrieve hybrid context, "
    "and draft a citation-oriented compliance note. Not legal advice."
)

with st.sidebar:
    store_dir = st.text_input(
        "Store directory",
        value=os.getenv("REGBOT_STORE", "./data/regbot_store"),
        help="Where Chroma + manifest.json are written.",
    )
    st.markdown(
        "**Default:** local [Ollama](https://ollama.com) (`REGBOT_OLLAMA_MODEL`, e.g. `llama3`). "
        "For OpenAI instead, set `REGBOT_LLM_PROVIDER=openai` and `OPENAI_API_KEY`. "
        "If the LLM is unreachable, a heuristic fallback runs."
    )

tab_ingest, tab_check, tab_chat = st.tabs(["Ingest policy", "Check consent", "Ask follow-up"])

with tab_ingest:
    uploaded = st.file_uploader("Policy PDF or .txt", type=["pdf", "txt"])
    reset = st.checkbox("Reset store before ingest", value=False)
    category = st.text_input("Category label (optional)", value="")
    if st.button("Ingest", type="primary") and uploaded is not None:
        suffix = Path(uploaded.name).suffix or ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getbuffer())
            tmp_path = tmp.name
        try:
            bot = RegBot(store_dir=store_dir)
            ok = bot.ingest_policy_documents(
                tmp_path,
                reset=reset,
                category=category.strip() or None,
            )
            st.success(
                "Ingest finished." if ok else "Ingest reported a problem (see terminal/logs)."
            )
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

with tab_check:
    consent_text = st.text_area("Paste consent or data-use language", height=240)
    filter_cat = st.text_input("Only use policy category (optional)", value="")
    top_k = st.slider("Retrieved chunks", min_value=3, max_value=16, value=8)
    if st.button("Analyze", type="primary"):
        bot = RegBot(store_dir=store_dir)
        report, chunks = bot.compliance_report_and_chunks(
            consent_text,
            category=filter_cat.strip() or None,
            top_k=int(top_k),
        )
        st.session_state["last_chunks"] = chunks
        st.session_state["last_consent"] = consent_text
        st.session_state["chat_messages"] = []
        st.subheader("Report")
        st.json(report)
        st.download_button(
            "Download JSON",
            data=json.dumps(report, indent=2, ensure_ascii=False),
            file_name="regbot_report.json",
            mime="application/json",
        )

with tab_chat:
    st.caption(
        "Uses the **same retrieved policy chunks** as your last **Analyze** on the Check consent tab. "
        "Exploratory Q&A only — not programmatically grounded like the JSON report. Not legal advice."
    )
    if not st.session_state.get("last_chunks"):
        st.info("Run **Analyze** on **Check consent** first to load chunks into this session.")
    else:
        for msg in st.session_state.get("chat_messages") or []:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        # st.chat_input cannot be placed inside st.tabs (Streamlit API); use form + text input instead.
        with st.form("followup_form", clear_on_submit=True):
            prompt = st.text_input(
                "Question about the retrieved policy context",
                placeholder="Type a question and click Send…",
                label_visibility="collapsed",
            )
            send = st.form_submit_button("Send")
        if send and prompt.strip():
            st.session_state.setdefault("chat_messages", []).append(
                {"role": "user", "content": prompt.strip()}
            )
            bot = RegBot(store_dir=store_dir)
            reply = chat_followup_policy_qa(
                st.session_state["last_chunks"],
                st.session_state.get("last_consent") or "",
                st.session_state["chat_messages"],
                api_key=bot.api_key,
            )
            st.session_state["chat_messages"].append({"role": "assistant", "content": reply})
            st.rerun()
