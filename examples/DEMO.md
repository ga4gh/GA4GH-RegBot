# GA4GH-RegBot End-to-End Demo

This demo shows GA4GH-RegBot in action with sample GA4GH policy documents.

## Quick Start (5 minutes)

### Prerequisites
- Python 3.8+
- Virtual environment activated
- Dependencies installed: \pip install -r requirements.txt\

### Step 1: Run the Ingestion Pipeline

\\\ash
cd examples
python run_demo.py --ingest-only
\\\

**Expected Output:**
\\\
Loading sample documents...
Loaded 3 documents from examples/data/
Processing document: sample_consent_policy.txt
Processing document: sample_privacy_policy.txt
Processing document: sample_genomic_framework.txt
Embedding chunks using sentence-transformers model...
✓ Ingested 12 chunks into vector store
✓ Demo ready!
\\\

### Step 2: Run the Full Demo (Ingestion + Queries)

\\\ash
python run_demo.py
\\\

**Expected Output:**
\\\
=====================================
GA4GH-RegBot Demo
=====================================

[INGESTION PHASE]
✓ 12 chunks ingested and stored

[RUNNING COMPLIANCE QUERIES]

---Query 1---
Q: "What are the consent requirements for genomic studies?"

A: According to GA4GH Consent Policy (Section 1):
   - Individuals must provide written or electronic informed consent
   - Consent must clearly specify purposes of research

---Query 2---
Q: "What security standards must be implemented?"

A: According to GA4GH Privacy Policy (Section 2):
   - Implement encryption for data at rest and in transit (AES-256)
   - Use TLS 1.2 or higher for network communication

---Query 3---
Q: "What are the eligible study types?"

A: According to Framework (Section 1):
   - Clinical Genomic Study
   - Population Genomic Study
   - Complex Disease Study
   - Rare Disease Study

=====================================
Demo completed successfully!
\\\

## How the Demo Works

1. **Ingestion:** Loads 3 sample GA4GH policy documents and embeds them
2. **Retrieval:** Uses semantic search to find relevant policy sections
3. **Query:** Demonstrates RegBot answering compliance questions

## Files Included
- \sample_consent_policy.txt\ - GA4GH Consent Policy excerpts
- \sample_privacy_policy.txt\ - GA4GH Privacy Policy excerpts
- \sample_genomic_framework.txt\ - Framework for Responsible Sharing excerpts
- \un_demo.py\ - Demo script

## Next Steps
Check out the main README for production usage
