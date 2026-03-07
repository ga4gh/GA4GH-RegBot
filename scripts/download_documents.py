"""
Download script for official GA4GH policy documents.

Downloads PDF documents from Google Drive and other sources into the
data/frameworks/ directory. Run this script once before ingesting documents.

Usage:
    python scripts/download_documents.py
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

# PDF documents hosted on Google Drive (file ID -> filename)
# These IDs were extracted from the official ga4gh.org product pages.
GOOGLE_DRIVE_DOCS = {
    "13V1fewFW7M38ztiU5WyW4UDL_q-yrvBk": "GA4GH_Consent_Policy_v2.0.pdf",
    "1QBZPO3eSJbtEcsnfaeZem1DE-z4yuhtl": "GA4GH_Data_Privacy_and_Security_Policy_v2.0.pdf",
}

# Direct URL downloads
DIRECT_URLS = {
    "https://raw.githubusercontent.com/EBISPOT/DUO/master/README.md": "DUO_Data_Use_Ontology_README.md",
}

# Framework document (already in GA4GH website, needs manual download)
MANUAL_DOWNLOAD_INSTRUCTIONS = """
=== MANUAL DOWNLOAD REQUIRED ===

The following documents need to be downloaded manually from ga4gh.org
and placed into the data/frameworks/ directory:

1. Framework for Responsible Sharing of Genomic Data
   URL: https://www.ga4gh.org/framework/
   -> Click "View in Google Drive" and download as PDF

2. Machine Readable Consent Guidance (MRCG)
   URL: https://www.ga4gh.org/product/machine-readable-consent-guidance/
   -> Click "USE THIS PRODUCT" and download the PDF

3. Consent Toolkit documents (from https://www.ga4gh.org/product/consent-policy/):
   - Consent Clauses for Genomic Research (2020)
   - Consent Toolkit: Clinical Genomic (v6.0)
   - Consent Toolkit: Rare Disease
   - Familial Consent Clauses (v1.0)
   - Consent Clauses for Large Scale Initiatives (v1.0)
   - Pediatric Consent to Genetic Research (v1.0)

   These are available at:
   https://www.ga4gh.org/our-products/ -> Filter by "Regulatory & Ethics Work Stream (REWS)"
"""


def download_from_google_drive(file_id: str, output_path: Path) -> bool:
    """Download a file from Google Drive by its file ID."""
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    try:
        print(f"  Downloading: {output_path.name}...")
        urllib.request.urlretrieve(url, str(output_path))
        size_kb = output_path.stat().st_size / 1024
        print(f"  -> Saved ({size_kb:.1f} KB)")
        return True
    except Exception as e:
        print(f"  -> FAILED: {e}")
        return False


def download_from_url(url: str, output_path: Path) -> bool:
    """Download a file from a direct URL."""
    try:
        print(f"  Downloading: {output_path.name}...")
        urllib.request.urlretrieve(url, str(output_path))
        size_kb = output_path.stat().st_size / 1024
        print(f"  -> Saved ({size_kb:.1f} KB)")
        return True
    except Exception as e:
        print(f"  -> FAILED: {e}")
        return False


def main():
    # Determine output directory
    project_root = Path(__file__).resolve().parent.parent
    frameworks_dir = project_root / "data" / "frameworks"
    frameworks_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("GA4GH RegBot - Policy Document Downloader")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    # Download from Google Drive
    print(f"\n[1/2] Downloading from Google Drive...")
    for file_id, filename in GOOGLE_DRIVE_DOCS.items():
        output_path = frameworks_dir / filename
        if output_path.exists():
            print(f"  Skipping (exists): {filename}")
            success_count += 1
        elif download_from_google_drive(file_id, output_path):
            success_count += 1
        else:
            fail_count += 1

    # Download from direct URLs
    print(f"\n[2/2] Downloading from direct URLs...")
    for url, filename in DIRECT_URLS.items():
        output_path = frameworks_dir / filename
        if output_path.exists():
            print(f"  Skipping (exists): {filename}")
            success_count += 1
        elif download_from_url(url, output_path):
            success_count += 1
        else:
            fail_count += 1

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Downloaded: {success_count}  |  Failed: {fail_count}")
    print(f"Output directory: {frameworks_dir}")

    # Check for text documents already in data/
    existing_txt = list((project_root / "data").glob("*.txt"))
    if existing_txt:
        print(f"\nAlso found {len(existing_txt)} text document(s) in data/:")
        for f in existing_txt:
            print(f"  - {f.name}")

    print(MANUAL_DOWNLOAD_INSTRUCTIONS)


if __name__ == "__main__":
    main()
