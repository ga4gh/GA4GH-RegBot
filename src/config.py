"""
Centralized configuration for GA4GH RegBot.

All settings can be overridden via environment variables or a .env file.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FRAMEWORKS_DIR = DATA_DIR / "frameworks"

# ── ChromaDB ─────────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(PROJECT_ROOT / "chroma_db"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "ga4gh_policies")

# ── Embedding Model ─────────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# ── Text Splitting ──────────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

# ── Retrieval ───────────────────────────────────────────────────────────
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "5"))

# ── Document Registry ───────────────────────────────────────────────────
# Maps filename patterns to category and subcategory for enriched metadata.
# The loader uses this to automatically tag chunks with the right category.
DOCUMENT_REGISTRY = {
    "Framework_Responsible_Sharing": {
        "category": "framework",
        "subcategory": "responsible_sharing",
        "display_name": "Framework for Responsible Sharing of Genomic Data",
    },
    "DUO_Data_Use_Ontology": {
        "category": "duo_mapping",
        "subcategory": "data_use_codes",
        "display_name": "Data Use Ontology (DUO) Reference",
    },
    "Machine_Readable_Consent": {
        "category": "duo_mapping",
        "subcategory": "consent_to_duo_mapping",
        "display_name": "Machine Readable Consent Guidance (MRCG)",
    },
    "Consent_Policy": {
        "category": "consent_requirements",
        "subcategory": "general",
        "display_name": "GA4GH Consent Policy (POL 002 v2.0)",
    },
    "Data_Privacy_Security": {
        "category": "privacy_security",
        "subcategory": "general",
        "display_name": "GA4GH Data Privacy and Security Policy (POL 001 v2.0)",
    },
    "Ethics_Review": {
        "category": "ethics_review",
        "subcategory": "mutual_recognition",
        "display_name": "GA4GH Ethics Review Recognition Policy",
    },
    "Consent_Toolkit": {
        "category": "consent_requirements",
        "subcategory": "toolkit_clauses",
        "display_name": "GA4GH Consent Toolkit - Consent Clauses",
    },
}
