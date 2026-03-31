import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import UNIVERSAL_MANDATORY_CHECKS
from src.retrieval.retriever import load_retriever
from src.compliance.checker import extract_text, detect_study_type, build_check_queue, run_compliance_check

st.title("RegBot - GA4GH Consent Form Compliance Checker")

# LLM backend selection
llm_choice = st.radio("LLM backend", ["Gemini 2.5 Flash (free)", "OpenAI GPT-4 (production)"])

if llm_choice.startswith("Gemini"):
    api_key = st.text_input("Gemini API Key", type="password")
else:
    api_key = st.text_input("OpenAI API Key", type="password")

uploaded_file = st.file_uploader("Upload consent form (PDF or TXT)", type=["pdf", "txt"])

if uploaded_file and api_key:
    if st.button("Run Compliance Check"):

        # Set env vars for checker.py
        if llm_choice.startswith("Gemini"):
            os.environ["LLM_BACKEND"]  = "gemini"
            os.environ["GEMINI_API_KEY"] = api_key
        else:
            os.environ["LLM_BACKEND"]    = "openai"
            os.environ["OPENAI_API_KEY"] = api_key

        # Extract text directly from BytesIO
        with st.spinner("Extracting text..."):
            consent_text = extract_text(uploaded_file, filename=uploaded_file.name)

        if not consent_text.strip():
            st.error("Could not extract text. Please check the file and try again.")
            st.stop()

        # Show study type and check count before LLM call
        detected_types = detect_study_type(consent_text)
        check_queue = build_check_queue(detected_types)

        st.write(f"**Detected study type:** {detected_types if detected_types else 'general'}")
        st.write(f"**Running {len(check_queue)} checks** ({len(UNIVERSAL_MANDATORY_CHECKS)} universal + {len(check_queue) - len(UNIVERSAL_MANDATORY_CHECKS)} conditional)")

        # Run pipeline
        with st.spinner("Running compliance checks..."):
            retriever = load_retriever()
            results = run_compliance_check(consent_text, retriever)

        # Split results
        universal = [r for r in results if r["check"] in UNIVERSAL_MANDATORY_CHECKS]
        conditional = [r for r in results if r["check"] not in UNIVERSAL_MANDATORY_CHECKS]

        # Tier 1
        st.subheader("Tier 1 - Universal Checks")
        for r in universal:
            icon = "✅" if r["verdict"] == "COMPLIANT" else "❌"
            st.write(f"{icon} **{r['check']}**")
            st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;{r['reason']}")
            st.caption(f"Citation: {r['citation']}")

        # Tier 2
        if conditional:
            st.subheader(f"Tier 2 - Conditional Checks ({detected_types})")
            for r in conditional:
                icon = "✅" if r["verdict"] == "COMPLIANT" else "❌"
                st.write(f"{icon} **{r['check']}**")
                st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;{r['reason']}")
                st.caption(f"Citation: {r['citation']}")
        else:
            st.info("No conditional checks triggered.")