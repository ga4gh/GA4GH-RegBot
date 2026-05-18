from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from openai import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam

from src.regbot.config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_OLLAMA_MODEL,
    MIN_TOKEN_OVERLAP,
    OLLAMA_API_KEY,
    OPENAI_MAX_RETRIES,
    llm_provider,
    ollama_openai_base_url,
)
from src.regbot.grounding import (
    allowed_chunk_ids,
    audit_report_grounding,
    filter_recommendations_by_token_overlap,
    normalize_recommendations,
)
from src.regbot.study_type import detect_study_type


def _format_evidence(chunks: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    parts: List[str] = []
    used = 0
    for c in chunks:
        meta = c.get("metadata") or {}
        header = (
            f"[chunk_id={c['id']} source={meta.get('source','?')} "
            f"page={meta.get('page',0)} category={meta.get('category','?')}]"
        )
        body = c.get("text", "").strip()
        block = f"{header}\n{body}\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts).strip()


def _fallback_report(
    consent: str,
    study_type: str,
    chunks: List[Dict[str, Any]],
    *,
    grounding_strict: bool = True,
) -> Dict[str, Any]:
    """Heuristic output when no LLM key is available; ties each recommendation to chunk ids."""
    consent_l = consent.lower()
    keywords = [
        "secondary use",
        "recontact",
        "withdraw",
        "data sharing",
        "international",
        "cloud",
        "identifiable",
        "pseudonym",
    ]
    missing = [k for k in keywords if k not in consent_l]
    status = "Partially Compliant" if len(missing) <= 3 else "Non-Compliant"
    ids_pool = [str(c["id"]) for c in chunks if c.get("id")]
    texts = [
        "Add explicit language on permitted secondary uses and any restrictions.",
        "Clarify withdrawal of consent and what happens to already-shared data.",
        "State whether data may be stored or processed outside the original jurisdiction.",
    ]
    recommendations: List[Dict[str, Any]] = []
    for i, t in enumerate(texts):
        ev = [ids_pool[i % len(ids_pool)]] if ids_pool else []
        recommendations.append({"text": t, "evidence_chunk_ids": ev})

    citations: List[Dict[str, str]] = []
    for c in chunks[:5]:
        citations.append(
            {
                "chunk_id": str(c["id"]),
                "reason": "Retrieved as potentially relevant policy context.",
            }
        )

    out: Dict[str, Any] = {
        "study_type": study_type,
        "status": status,
        "missing_elements": missing,
        "recommendations": recommendations,
        "citations": citations,
        "notes": (
            "LLM analysis disabled: REGBOT_LLM_PROVIDER=openai requires OPENAI_API_KEY. "
            "Default provider is local Ollama (no cloud key). "
            "This is a lightweight keyword gap check, not legal advice."
        ),
    }
    allow = allowed_chunk_ids(chunks)
    out["grounding"] = audit_report_grounding(
        out,
        allow,
        require_evidence_per_recommendation=grounding_strict,
        validate_supplementary_citations=True,
    )
    # Offline path: do not apply token-overlap drops (generic text may not lexically match policy).
    out["grounding"]["overlap"] = {
        "skipped": True,
        "reason": "Keyword fallback does not apply REGBOT_MIN_TOKEN_OVERLAP filtering.",
    }
    out["grounding_attempts"] = 1
    return out


def _fallback_after_api_error(
    consent_text: str,
    study_type: str,
    chunks: List[Dict[str, Any]],
    *,
    grounding_strict: bool,
    detail: str,
) -> Dict[str, Any]:
    """Offline heuristic when the LLM request fails (quota, auth, Ollama down, network, etc.)."""
    out = _fallback_report(
        consent_text,
        study_type,
        chunks,
        grounding_strict=grounding_strict,
    )
    out["notes"] = (
        "LLM request did not complete; using offline keyword heuristic instead. "
        "Not legal advice. "
        f"({detail})"
    )
    return out


def analyze_compliance(
    consent_text: str,
    chunks: List[Dict[str, Any]],
    *,
    study_type: str,
    api_key: Optional[str],
    model: Optional[str] = None,
    max_grounding_retries: int = 1,
    grounding_strict: bool = True,
    min_token_overlap: Optional[float] = None,
) -> Dict[str, Any]:
    overlap_floor = MIN_TOKEN_OVERLAP if min_token_overlap is None else float(min_token_overlap)

    if not chunks:
        empty: Dict[str, Any] = {
            "study_type": study_type,
            "status": "Unknown",
            "missing_elements": [],
            "recommendations": [
                {
                    "text": (
                        "Ingest at least one GA4GH policy document into the local store "
                        "before checking compliance."
                    ),
                    "evidence_chunk_ids": [],
                }
            ],
            "citations": [],
            "notes": "No retrieved policy context.",
            "grounding": {
                "ok": False,
                "issues": ["No retrieved chunks; evidence_chunk_ids cannot be grounded."],
                "allowed_chunk_count": 0,
                "recommendation_count": 1,
                "invalid_evidence_chunk_ids": [],
            },
            "grounding_attempts": 0,
        }
        return empty

    provider = llm_provider()
    use_ollama = provider == "ollama"
    use_openai = provider == "openai" and bool(api_key)
    if not use_ollama and not use_openai:
        return _fallback_report(
            consent_text,
            study_type,
            chunks,
            grounding_strict=grounding_strict,
        )

    allow = allowed_chunk_ids(chunks)
    evidence = _format_evidence(chunks)
    if use_ollama:
        model_name = model or DEFAULT_OLLAMA_MODEL
        client = OpenAI(
            base_url=ollama_openai_base_url(),
            api_key=OLLAMA_API_KEY,
            max_retries=OPENAI_MAX_RETRIES,
        )
    else:
        model_name = model or DEFAULT_LLM_MODEL
        client = OpenAI(api_key=api_key, max_retries=OPENAI_MAX_RETRIES)

    system = (
        "You are a research compliance assistant for genomic data sharing. "
        "You must only use the POLICY EXCERPTS block as evidence. "
        "If the excerpts do not contain enough information, say so explicitly. "
        "Return JSON only, no markdown. "
        "Each recommendation MUST be an object with keys: "
        '"text" (string) and "evidence_chunk_ids" (array of strings). '
        "Every string in evidence_chunk_ids MUST be copied exactly from a "
        "[chunk_id=...] header in POLICY EXCERPTS (no invented ids). "
        "Each recommendation must have at least one evidence_chunk_id. "
        "Write recommendation text so its wording substantially overlaps the vocabulary "
        "of the cited excerpts (shared terms/phrases), not generic boilerplate unrelated to those chunks. "
        "Optional: citations (array of {chunk_id, reason}) for extra references; "
        "those chunk_id values must also satisfy the same allow-list."
    )
    base_user = (
        f"STUDY_TYPE_GUESS: {study_type}\n\n"
        f"POLICY EXCERPTS:\n{evidence}\n\n"
        f"CONSENT_OR_DATA_USE_TEXT:\n{consent_text.strip()}\n\n"
        "Return a JSON object with keys: "
        "study_type (string), status (one of: Compliant, Partially Compliant, Non-Compliant, Unknown), "
        "missing_elements (array of strings), "
        "recommendations (array of objects, each with text and evidence_chunk_ids), "
        "citations (optional array of objects with chunk_id, reason), "
        "notes (optional string)."
    )

    suffix = ""
    attempts = 0
    max_attempts = max(1, max_grounding_retries + 1)
    out: Dict[str, Any] = {}
    while attempts < max_attempts:
        attempts += 1
        user = base_user + suffix
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            try:
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
            except BadRequestError:
                # Ollama / some local models do not support json_object response_format.
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.2,
                )
        except (RateLimitError, AuthenticationError) as e:
            msg = str(getattr(e, "message", e))[:400]
            return _fallback_after_api_error(
                consent_text,
                study_type,
                chunks,
                grounding_strict=grounding_strict,
                detail=f"{type(e).__name__}: {msg}",
            )
        except APIConnectionError as e:
            msg = str(getattr(e, "message", e))[:400]
            return _fallback_after_api_error(
                consent_text,
                study_type,
                chunks,
                grounding_strict=grounding_strict,
                detail=f"{type(e).__name__}: {msg}",
            )
        raw = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", raw)
            data = json.loads(m.group(0)) if m else {}

        out = {
            "study_type": str(data.get("study_type", study_type)),
            "status": str(data.get("status", "Unknown")),
            "missing_elements": list(data.get("missing_elements") or []),
            "recommendations": normalize_recommendations(data.get("recommendations")),
            "citations": list(data.get("citations") or []),
        }
        if data.get("notes"):
            out["notes"] = str(data["notes"])
        out["model"] = model_name

        audit = audit_report_grounding(
            out,
            allow,
            require_evidence_per_recommendation=grounding_strict,
            validate_supplementary_citations=True,
        )

        if not audit["ok"]:
            out["grounding"] = audit
            out["grounding_attempts"] = attempts
            if attempts >= max_attempts:
                note = (
                    " Model output failed programmatic citation grounding checks after retries; "
                    "treat recommendations as ungrounded."
                )
                out["notes"] = (out.get("notes") or "") + note
                return out
            suffix = (
                "\n\nGROUNDING_FIX_REQUIRED:\n"
                + "\n".join(f"- {issue}" for issue in audit["issues"])
                + "\nAllowed chunk_id values (copy exactly into evidence_chunk_ids):\n"
                + json.dumps(sorted(allow))
                + "\nReturn the full JSON object again. "
                "Each recommendations[] item must include non-empty evidence_chunk_ids "
                "from that allow-list."
            )
            continue

        filt, ometa = filter_recommendations_by_token_overlap(
            out["recommendations"],
            chunks,
            min_overlap=overlap_floor,
        )
        out["recommendations"] = filt
        merged = dict(audit)
        merged["recommendation_count"] = len(filt)
        merged["overlap"] = ometa
        out["grounding"] = merged

        dropped_all = bool(ometa.get("dropped_all")) and overlap_floor > 0
        if dropped_all:
            issues = list(merged.get("issues", []))
            issues.append(
                "All recommendations removed: token overlap between recommendation text and "
                f"cited chunk text is below threshold ({overlap_floor}). "
                "Rewrite each recommendation to use wording aligned with the cited excerpts."
            )
            merged["issues"] = issues
            merged["ok"] = False
            out["grounding"] = merged
            out["grounding_attempts"] = attempts
            if attempts >= max_attempts:
                out["notes"] = (
                    out.get("notes", "")
                    + " Recommendations failed token-overlap checks after retries."
                )
                return out
            suffix = (
                "\n\nTOKEN_OVERLAP_FIX_REQUIRED:\n"
                f"- Minimum token recall vs cited chunks: {overlap_floor}\n"
                "- Paraphrase the cited excerpt ideas using overlapping terms/phrases from those excerpts.\n"
                "- Keep evidence_chunk_ids pointing to the chunks your text is grounded in.\n"
                "Return the full JSON object again."
            )
            continue

        merged["ok"] = True
        out["grounding"] = merged
        out["grounding_attempts"] = attempts
        return out

    return out


def chat_followup_policy_qa(
    chunks: List[Dict[str, Any]],
    consent_text: str,
    messages: List[Dict[str, str]],
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Multi-turn Q&A using only retrieved chunks as policy evidence (same headers as compliance).
    ``messages`` are prior turns: {"role": "user"|"assistant", "content": "..."}.
    Does not replace programmatic JSON grounding; for exploratory follow-up only. Not legal advice.
    """
    if not chunks:
        return "No policy chunks available. Run **Analyze** on the Check consent tab first."

    provider = llm_provider()
    use_ollama = provider == "ollama"
    use_openai = provider == "openai" and bool(api_key)
    if not use_ollama and not use_openai:
        return (
            "Chat needs an LLM: start Ollama or set REGBOT_LLM_PROVIDER=openai with OPENAI_API_KEY."
        )

    if use_ollama:
        model_name = model or DEFAULT_OLLAMA_MODEL
        client = OpenAI(
            base_url=ollama_openai_base_url(),
            api_key=OLLAMA_API_KEY,
            max_retries=OPENAI_MAX_RETRIES,
        )
    else:
        model_name = model or DEFAULT_LLM_MODEL
        client = OpenAI(api_key=api_key, max_retries=OPENAI_MAX_RETRIES)

    evidence = _format_evidence(chunks)
    study_guess = detect_study_type(consent_text)
    system = (
        "You are a research compliance assistant for genomic data sharing. Not legal advice.\n\n"
        "Two kinds of sources:\n"
        "(1) GA4GH/policy requirements: use ONLY the POLICY EXCERPTS below. "
        "Cite chunk_id from [chunk_id=...] headers when you reference policy text.\n"
        "(2) The participant consent / data-use text: use CONSENT_OR_DATA_USE_TEXT below. "
        "For **study type** as used in the compliance JSON report, use this exact pipeline label "
        "(keyword heuristic, same as field `study_type` in Check consent):\n"
        f"STUDY_TYPE_GUESS: {study_guess}\n"
        "If the user asks what the study type is, answer with STUDY_TYPE_GUESS and say it matches "
        "the automated keyword classifier; optionally quote a short supporting phrase from the consent text. "
        "Do not invent a different category (e.g. 'research study') unless the user asks for informal wording "
        "— in that case, still mention STUDY_TYPE_GUESS first.\n\n"
        f"POLICY EXCERPTS:\n{evidence}\n\n"
        "CONSENT_OR_DATA_USE_TEXT:\n"
        f"{consent_text.strip()}"
    )

    history: List[ChatCompletionMessageParam] = [{"role": "system", "content": system}]
    for m in messages[-24:]:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        history.append({"role": role, "content": content})

    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=history,
            temperature=0.3,
        )
    except (RateLimitError, AuthenticationError, APIConnectionError, BadRequestError) as e:
        return f"Could not reach the LLM: {type(e).__name__}: {str(e)[:400]}"

    return (resp.choices[0].message.content or "").strip() or "(empty reply)"
