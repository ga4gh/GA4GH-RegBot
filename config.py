# config.py — GA4GH RegBot

# Paths
FRAMEWORKS_PATH = "data/frameworks/"
CHROMA_PATH     = "chroma_db/"
DUO_CSV_PATH    = "data/frameworks/duo.csv"

# Embedding
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Chunking
CHUNK_SIZE    = 500
CHUNK_OVERLAP = 50

# Source names for citations
SOURCE_NAMES = {
    "framework_responsible_sharing.pdf":    "Framework for Responsible Sharing of Genomic Data",
    "consent_policy.pdf":                   "GA4GH Consent Policy (POL 002 v2.0)",
    "data_privacy_security_policy.pdf":     "GA4GH Data Privacy and Security Policy (POL 001 v2.0)",
    "mrcg.pdf":                             "Machine Readable Consent Guidance (MRCG)",
    "consent_toolkit_genomic_research.pdf": "Consent Clauses for Genomic Research (2020)",
    "consent_toolkit_clinical_genomic.pdf": "Consent Toolkit — Clinical Genomic (D015 v6.0)",
    "consent_toolkit_rare_disease.pdf":     "Consent Toolkit — Rare Disease",
    "consent_toolkit_familial.pdf":         "Familial Consent Clauses (D011 v1.0)",
    "consent_toolkit_large_scale.pdf":      "Consent Clauses for Large Scale Initiatives (D014 v1.0)",
    "consent_toolkit_pediatric.pdf":        "Pediatric Consent to Genetic Research (D012a v1.0)",
    "duo.csv":                              "Data Use Ontology (DUO v2021-02-23)",
}

# Categories for chunk metadata
CATEGORIES = {
    "framework_responsible_sharing.pdf":    "foundational_principles",
    "consent_policy.pdf":                   "consent_requirements",
    "data_privacy_security_policy.pdf":     "privacy_security_requirements",
    "mrcg.pdf":                             "duo_mapping",
    "duo.csv":                              "duo_terms",
    "consent_toolkit_genomic_research.pdf": "consent_clauses",
    "consent_toolkit_clinical_genomic.pdf": "consent_clauses",
    "consent_toolkit_rare_disease.pdf":     "consent_clauses",
    "consent_toolkit_familial.pdf":         "consent_clauses",
    "consent_toolkit_large_scale.pdf":      "consent_clauses",
    "consent_toolkit_pediatric.pdf":        "consent_clauses",
}

# Subcategories for toolkit documents
SUBCATEGORIES = {
    "consent_toolkit_genomic_research.pdf": "genomic_research",
    "consent_toolkit_clinical_genomic.pdf": "clinical_genomic",
    "consent_toolkit_rare_disease.pdf":     "rare_disease",
    "consent_toolkit_familial.pdf":         "familial",
    "consent_toolkit_large_scale.pdf":      "large_scale",
    "consent_toolkit_pediatric.pdf":        "pediatric",
}

# Study type auto-detection keywords
STUDY_TYPE_KEYWORDS = {
    "clinical_genomic": [
        "clinical", "clinical genetic", "genetic testing", "diagnostic",
        "pathogenic", "variant of uncertain significance", "VUS",
        "genetic counsell", "clinical laboratory", "whole genome sequencing",
    ],
    "familial": [
        "family member", "family members", "relatives", "familial",
        "hereditary", "next of kin", "genetic family",
    ],
    "pediatric": [
        "child", "children", "minor", "pediatric", "paediatric",
        "parent", "guardian", "assent", "age of majority",
    ],
    "rare_disease": [
        "rare disease", "rare condition", "undiagnosed", "orphan disease",
        "matchmaking", "patient registry", "rare disorder",
    ],
    "large_scale": [
        "biobank", "biobanking", "population study", "cohort study",
        "large scale", "large-scale", "longitudinal",
    ],
}

# Universal checks — run on every consent form
UNIVERSAL_MANDATORY_CHECKS = [
    "data_sharing_purpose",
    "withdrawal_rights",
    "reidentification_risk",
    "data_categories_disclosed",
    "third_party_sharing",
    "anonymization_deidentification",
    "incidental_findings_policy",
    "data_storage_duration",
]

# Conditional checks — triggered by detected study type
CONDITIONAL_MANDATORY_CHECKS = {
    "clinical_genomic": [
        "results_reporting_policy",
        "genomic_testing_limitations",
        "recontact_policy",
        "genetic_discrimination_risk",
        "dna_data_destruction_policy",
    ],
    "familial": [
        "family_member_disclosure_approach",
        "discrimination_stigmatization_warning",
    ],
    "pediatric": [
        "minor_assent_process",
        "recontact_at_majority",
    ],
    "rare_disease": [
        "data_linkage_matchmaking",
        "family_enrollment_policy",
    ],
    "large_scale": [
        "secondary_research_use",
        "biobank_storage_duration",
    ],
}

# Query strings used to retrieve relevant GA4GH chunks from ChromaDB per check
CHECK_QUERIES = {

    # --- Universal ---
    "data_sharing_purpose":           "purpose of data sharing genomic research why data is shared",
    "withdrawal_rights":              "right to withdraw opt-out consent data sharing",
    "reidentification_risk":          "risk of re-identification genomic data participants",
    "data_categories_disclosed":      "what types of data are collected and shared genomic",
    "third_party_sharing":            "sharing data with third parties institutions cross-border commercial",
    "anonymization_deidentification": "de-identification anonymization pseudonymization process genomic data",
    "incidental_findings_policy":     "secondary incidental findings return of results participants",
    "data_storage_duration":          "data storage duration how long samples stored biorepository",

    # --- Clinical Genomic ---
    "results_reporting_policy":       "what results are reported positive pathogenic negative uncertain VUS",
    "genomic_testing_limitations":    "limitations of genomic testing what test cannot detect",
    "recontact_policy":               "recontact participants future results reinterpretation",
    "genetic_discrimination_risk":    "genetic discrimination employment insurance stigmatization",
    "dna_data_destruction_policy":    "destruction of DNA data samples withdrawal request",

    # --- Familial ---
    "family_member_disclosure_approach":    "family member disclosure results genetic relatives duty to warn",
    "discrimination_stigmatization_warning":"discrimination stigmatization family members genetic information employers insurers",

    # --- Pediatric ---
    "minor_assent_process":    "assent minor child pediatric research participation verbal written",
    "recontact_at_majority":   "recontact majority legal age child data samples continued participation",

    # --- Rare Disease ---
    "data_linkage_matchmaking": "data linkage matchmaking rare disease patient registry recontact",
    "family_enrollment_policy": "family enrollment familial participation rare disease diagnosis",

    # --- Large Scale ---
    "secondary_research_use":   "secondary research use samples biobank future studies commercial",
    "biobank_storage_duration": "biobank storage duration samples indefinitely population study",
}