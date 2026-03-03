GA4GH-RegBot: Compliance Assistant
Status: Proposal Stage for GSoC 2026

Overview
RegBot is an LLM-powered tool designed to help researchers map their consent forms against GA4GH regulatory frameworks. It uses RAG (Retrieval-Augmented Generation) to flag compliance gaps automatically.

Architecture (Planned)
Core: Python

LLM Framework: LangChain / LlamaIndex

Vector Store: ChromaDB / FAISS

UI: Streamlit

Roadmap
Phase 1: Ingest GA4GH "Framework for Responsible Sharing" policy documents.

Phase 2: Build RAG pipeline for clause extraction.

Phase 3: Develop Streamlit frontend for user uploads.

Planning
See `PLAN.md` for the draft GSoC 2026 implementation scope, deliverables, and timeline.
