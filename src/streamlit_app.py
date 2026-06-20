from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from dotenv import load_dotenv

from src.main import RegBot
from src.regbot.compliance import chat_followup_policy_qa
from src.regbot.corpus_manifest import load_corpus_manifest
from src.regbot.ingestion import read_manifest
from src.regbot.jurisdiction import (
    JURISDICTION_CODES,
    chunk_jurisdiction_tags,
    jurisdiction_matches,
    jurisdiction_option_label,
    jurisdiction_options_for_ui,
    parse_jurisdiction_filter,
)

st.set_page_config(page_title="GA4GH-RegBot", layout="wide")
load_dotenv()

_JURISDICTION_UI_OPTIONS = {code: label for code, label in jurisdiction_options_for_ui()}
_CORPUS_MANIFEST_PATH = str(_ROOT / "docs" / "corpus_manifest.yaml")
_TIER_LABELS = {
    "P0": "P0 — GA4GH / REWS framework",
    "P1": "P1 — GDPR & consent-code briefs",
    "P2": "P2 — Regional law excerpts",
}


def _corpus_documents(manifest_path: str = _CORPUS_MANIFEST_PATH) -> List[Dict[str, Any]]:
    try:
        data = load_corpus_manifest(manifest_path)
        return list(data.get("documents") or [])
    except Exception:
        return []


def _corpus_source_urls(docs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, str]:
    docs = docs if docs is not None else _corpus_documents()
    out: Dict[str, str] = {}
    for doc in docs:
        doc_id = str(doc.get("document_id") or "").strip()
        url = doc.get("source_url")
        if doc_id and url and str(url).strip():
            out[doc_id] = str(url).strip()
    return out


def _render_corpus_document_row(doc: Dict[str, Any], *, key_prefix: str) -> None:
    doc_id = str(doc.get("document_id") or "")
    title = str(doc.get("title") or doc_id or "Untitled")
    tier = str(doc.get("tier") or "—")
    juris = ", ".join(str(j) for j in (doc.get("jurisdiction") or []))
    ingested = "yes" if doc.get("ingested_at") else "not yet"
    col_info, col_link = st.columns([5, 2])
    with col_info:
        st.markdown(f"**{title}**")
        st.caption(f"`{doc_id}` · {tier} · {juris} · ingested: {ingested}")
    with col_link:
        url = doc.get("source_url")
        if url and str(url).strip():
            st.link_button(
                "Open source",
                str(url).strip(),
                use_container_width=True,
            )
        else:
            st.caption("No public URL")


def _render_corpus_inventory(
    docs: List[Dict[str, Any]],
    *,
    key_prefix: str,
    region_filter: Optional[str] = None,
) -> None:
    if not docs:
        st.warning("No corpus entries found in `docs/corpus_manifest.yaml`.")
        return
    filtered = docs
    if region_filter:
        want = region_filter.upper()
        filtered = [
            d for d in docs if want in {str(j).upper() for j in (d.get("jurisdiction") or [])}
        ]
    if region_filter and not filtered:
        st.info(f"No manifest documents tagged `{region_filter}`.")
        return
    by_tier: Dict[str, List[Dict[str, Any]]] = {"P0": [], "P1": [], "P2": []}
    for doc in filtered:
        tier = str(doc.get("tier") or "P2").upper()
        by_tier.setdefault(tier, []).append(doc)
    for tier in ("P0", "P1", "P2"):
        tier_docs = by_tier.get(tier) or []
        if not tier_docs:
            continue
        label = _TIER_LABELS.get(tier, tier)
        st.markdown(f"#### {label}")
        for doc in tier_docs:
            _render_corpus_document_row(doc, key_prefix=f"{key_prefix}_{tier}")
        st.divider()


def _bot(store_dir: str) -> RegBot:
    return RegBot(store_dir=store_dir)


def _stored_jurisdictions(store_dir: str) -> List[str]:
    try:
        bot = _bot(store_dir)
        return bot.list_store_jurisdictions()
    except Exception:
        return []


def _chunks_for_region(store_dir: str, region: str) -> List[Dict[str, Any]]:
    chunks = read_manifest(store_dir)
    selected = parse_jurisdiction_filter([region])
    out: List[Dict[str, Any]] = []
    for rec in chunks:
        if jurisdiction_matches(rec.get("metadata"), selected):
            out.append(rec)
    return out


def _jurisdiction_multiselect(
    key: str,
    *,
    label: str,
    help_text: str,
    default: Optional[List[str]] = None,
) -> List[str]:
    default = default or []
    options = list(JURISDICTION_CODES)
    labels = [_JURISDICTION_UI_OPTIONS.get(c, c) for c in options]
    selected_labels = st.multiselect(
        label,
        options=labels,
        default=[
            _JURISDICTION_UI_OPTIONS.get(c, c) for c in default if c in _JURISDICTION_UI_OPTIONS
        ],
        help=help_text,
        key=key,
    )
    label_to_code = {_JURISDICTION_UI_OPTIONS[c]: c for c in options}
    return [label_to_code[lab] for lab in selected_labels if lab in label_to_code]


def _render_chunk_cards(
    chunks: List[Dict[str, Any]],
    *,
    empty_hint: str,
    source_urls: Optional[Dict[str, str]] = None,
) -> None:
    if not chunks:
        st.warning(empty_hint)
        return
    urls = source_urls or {}
    for ch in chunks:
        meta = ch.get("metadata") or {}
        tags = sorted(chunk_jurisdiction_tags(meta))
        tag_str = ", ".join(tags) if tags else "—"
        title = f"`{ch.get('id', '')}` · {meta.get('source', '?')} p.{meta.get('page', '?')} · **{tag_str}**"
        with st.expander(title):
            doc_id = str(meta.get("document_id") or meta.get("category") or "")
            source_url = urls.get(doc_id)
            cap = f"Category: {meta.get('category', '—')} · Jurisdiction: {tag_str}"
            if doc_id:
                cap += f" · document_id: `{doc_id}`"
            st.caption(cap)
            if source_url:
                st.link_button(
                    "Open original source page",
                    source_url,
                )
            st.text((ch.get("text") or "")[:2000])


st.title("GA4GH-RegBot")
st.caption(
    "Prototype assistant: ingest GA4GH-style policy excerpts, retrieve hybrid context, "
    "and draft a citation-oriented compliance note. Not legal advice."
)

_corpus_docs = _corpus_documents()
_corpus_urls = _corpus_source_urls(_corpus_docs)

with st.sidebar:
    store_dir = st.text_input(
        "Store directory",
        value=os.getenv("REGBOT_STORE", "./data/regbot_store"),
        help="Where Chroma + manifest.json are written.",
    )
    st.markdown("### Corpus by region")
    in_store = _stored_jurisdictions(store_dir)
    if in_store:
        st.caption("Jurisdictions tagged in the current store:")
        for code in in_store:
            st.markdown(f"- **{code}** — {jurisdiction_option_label(code).split(' — ', 1)[-1]}")
    else:
        st.caption(
            "No jurisdiction tags in the store yet. When ingesting policy, pick a region "
            "(SG, CN, JP, …) so retrieval can be scoped."
        )
    st.caption(f"**{len(_corpus_docs)}** documents in corpus manifest — see **Corpus** tab.")
    st.markdown(
        "**Default:** local [Ollama](https://ollama.com) (`REGBOT_OLLAMA_MODEL`, e.g. `llama3`). "
        "For OpenAI instead, set `REGBOT_LLM_PROVIDER=openai` and `OPENAI_API_KEY`. "
        "If the LLM is unreachable, a heuristic fallback runs."
    )

tab_ingest, tab_corpus, tab_browse, tab_check, tab_chat = st.tabs(
    ["Ingest policy", "Corpus", "Browse by region", "Check consent", "Ask follow-up"]
)

with tab_ingest:
    uploaded = st.file_uploader("Policy PDF or .txt", type=["pdf", "txt"])
    reset = st.checkbox("Reset store before ingest", value=False)
    category = st.text_input("Category label (optional)", value="")
    ingest_codes = list(JURISDICTION_CODES)
    ingest_labels = [_JURISDICTION_UI_OPTIONS[c] for c in ingest_codes]
    ingest_pick = st.selectbox(
        "Jurisdiction for this document",
        options=ingest_labels,
        index=ingest_labels.index(_JURISDICTION_UI_OPTIONS["GA4GH"])
        if _JURISDICTION_UI_OPTIONS["GA4GH"] in ingest_labels
        else 0,
        help="Tags every chunk from this upload (DESIGN.md §3.1). Required for region-scoped retrieval.",
    )
    ingest_jurisdiction = ingest_codes[ingest_labels.index(ingest_pick)]
    if st.button("Ingest", type="primary") and uploaded is not None:
        suffix = Path(uploaded.name).suffix or ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getbuffer())
            tmp_path = tmp.name
        try:
            bot = _bot(store_dir)
            ok = bot.ingest_policy_documents(
                tmp_path,
                reset=reset,
                category=category.strip() or None,
                jurisdiction=ingest_jurisdiction,
            )
            st.success(
                f"Ingest finished ({ingest_jurisdiction})."
                if ok
                else "Ingest reported a problem (see terminal/logs)."
            )
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

with tab_corpus:
    st.markdown(
        "Regulatory corpus inventory from `docs/corpus_manifest.yaml`. "
        "Use **Open source** to view the original GA4GH page, GDPR brief, or statute reference."
    )
    corpus_region = st.selectbox(
        "Filter by jurisdiction",
        options=["All"] + list(JURISDICTION_CODES),
        format_func=lambda c: "All jurisdictions" if c == "All" else jurisdiction_option_label(c),
        key="corpus_region_filter",
    )
    region_arg = None if corpus_region == "All" else corpus_region
    _render_corpus_inventory(
        _corpus_docs,
        key_prefix="corpus_tab",
        region_filter=region_arg,
    )

with tab_browse:
    st.markdown(
        "View ingested policy chunks **by jurisdiction** without running a compliance check. "
        "Useful to see what is in the corpus for Singapore, Japan, GA4GH framework docs, etc."
    )
    browse_region = st.selectbox(
        "Region / jurisdiction",
        options=list(JURISDICTION_CODES),
        format_func=lambda c: jurisdiction_option_label(c),
        key="browse_region_select",
    )
    browse_limit = st.slider("Max chunks to show", min_value=5, max_value=80, value=25)
    if st.button("Load chunks", type="primary", key="browse_load"):
        region_chunks = _chunks_for_region(store_dir, browse_region)
        st.session_state["browse_chunks"] = region_chunks[: int(browse_limit)]
        st.session_state["browse_loaded_region"] = browse_region
    if st.session_state.get("browse_chunks") is not None:
        region = st.session_state.get("browse_loaded_region", browse_region)
        chunks = st.session_state["browse_chunks"]
        st.subheader(f"{region} — {len(chunks)} chunk(s) shown")
        _render_chunk_cards(
            chunks,
            empty_hint=(
                f"No chunks tagged `{region}` in this store. "
                "Ingest a document with that jurisdiction, or try another region."
            ),
            source_urls=_corpus_urls,
        )

with tab_check:
    consent_text = st.text_area("Paste consent or data-use language", height=240)
    col_cat, col_jur = st.columns(2)
    with col_cat:
        filter_cat = st.text_input("Only use policy category (optional)", value="")
    with col_jur:
        filter_jurisdictions = _jurisdiction_multiselect(
            "check_jurisdiction",
            label="Scope to jurisdiction(s)",
            help_text=(
                "Leave empty to search all ingested policy. Select one or more regions "
                "(e.g. SG + GA4GH) to narrow hybrid retrieval."
            ),
            default=st.session_state.get("last_jurisdictions") or [],
        )
    top_k = st.slider("Retrieved chunks", min_value=3, max_value=16, value=8)
    if st.button("Analyze", type="primary"):
        bot = _bot(store_dir)
        jur_filter = parse_jurisdiction_filter(filter_jurisdictions)
        report, chunks = bot.compliance_report_and_chunks(
            consent_text,
            category=filter_cat.strip() or None,
            jurisdiction=jur_filter,
            top_k=int(top_k),
        )
        st.session_state["last_chunks"] = chunks
        st.session_state["last_consent"] = consent_text
        st.session_state["last_jurisdictions"] = filter_jurisdictions
        st.session_state["chat_messages"] = []
        scope = ", ".join(jur_filter) if jur_filter else "all jurisdictions"
        st.subheader("Report")
        st.caption(f"Retrieval scope: **{scope}** · {len(chunks)} chunk(s) used")
        st.json(report)
        st.download_button(
            "Download JSON",
            data=json.dumps(report, indent=2, ensure_ascii=False),
            file_name="regbot_report.json",
            mime="application/json",
        )
        with st.expander("Retrieved policy excerpts", expanded=bool(chunks)):
            _render_chunk_cards(
                chunks,
                empty_hint=(
                    "No chunks matched this query and jurisdiction filter. "
                    "Try clearing the jurisdiction filter or ingest policy for that region."
                ),
                source_urls=_corpus_urls,
            )

with tab_chat:
    st.caption(
        "Uses the **same retrieved policy chunks** as your last **Analyze** on the Check consent tab. "
        "Exploratory Q&A only — not programmatically grounded like the JSON report. Not legal advice."
    )
    if st.session_state.get("last_jurisdictions"):
        st.caption(
            "Last analysis jurisdictions: " + ", ".join(st.session_state["last_jurisdictions"])
        )
    if not st.session_state.get("last_chunks"):
        st.info("Run **Analyze** on **Check consent** first to load chunks into this session.")
    else:
        for msg in st.session_state.get("chat_messages") or []:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
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
            bot = _bot(store_dir)
            reply = chat_followup_policy_qa(
                st.session_state["last_chunks"],
                st.session_state.get("last_consent") or "",
                st.session_state["chat_messages"],
                api_key=bot.api_key,
            )
            st.session_state["chat_messages"].append({"role": "assistant", "content": reply})
            st.rerun()
