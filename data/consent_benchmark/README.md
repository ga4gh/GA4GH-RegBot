# Consent-form benchmark documents

Participant-facing consent documents used as *queries* in the consent → provision benchmark
(`examples/eval/consent_docs.yaml`). Every document is fetched from its publisher by
`python -I tools/experiments/fetch_consent_docs.py`, which validates the download before keeping
it; the reuse terms below are as stated by the publisher at fetch time. Texts are committed only
where the terms clearly allow redistribution; the others are fetch-only (see `.gitignore`).
Clause boundaries are frozen by hash in the benchmark file and the clause texts are regenerated
locally by `python tools/experiments/consent_docs.py draft`.

| doc_id | title | origin | language | reuse terms (as stated) | in repo |
|---|---|---|---|---|---|
| `us-nih-osp-secondary-research-sample` | NIH OSP — Informed Consent for Secondary Research with Data and Biospecimens: Points to Consider and Sample Language (May 2022) | US | en | US federal government work; no licence stated (public domain) | yes |
| `us-nhgri-gds-sample-language` | NHGRI — Genomic Data Sharing Policy: sample informed consent language | US | en | NHGRI web content is in the public domain unless otherwise indicated | yes |
| `us-nih-irb-consent-library` | NIH IRB Consent Library v18 (OHSRP, February 2026) | US | en | US federal government work; no licence stated (public domain) | yes |
| `us-all-of-us-consent-to-join` | All of Us Research Program — Consent to Join (English) | US | en | Hosted by NHGRI as a sample document; drafted for NIH by VUMC; public-domain status likely but not confirmed — attribute | yes |
| `us-1000-genomes-consent` | 1000 Genomes Project — sample consent form | US / international | en | Hosted by NHGRI as a sample document; attribute | yes |
| `us-emerge-consent` | eMERGE Network — consent and community consultation template | US | en | Hosted by NHGRI as a sample document; consortium-authored; attribute | yes |
| `us-gtex-live-donor-consent` | GTEx — live donor informed consent template | US | en | Hosted by NHGRI as a sample document; attribute | yes |
| `us-beskow-simplified-biobank-consent` | Beskow et al. (2010) — simplified consent form for biobanking (PLoS ONE S1) | US | en | CC BY (PLoS ONE open-access article supplement) | yes |
| `eu-uppsala-biobank-registry-consent-template` | Uppsala University CRB — Informed consent guide and template for biobank and registry-based research | EU (Sweden) | en | CC BY 4.0 (Zenodo record 3928446) | yes |
| `ee-estonian-biobank-gene-donor-consent` | Estonian Biobank — Gene Donor Consent Form (annex to Regulation No 39 of 2019) | EU (Estonia) | en | Annex to a ministerial regulation; no licence stated on page | fetch-only |
| `kr-bioethics-form-34-research-consent` | Korea — Bioethics and Safety Act Enforcement Rule, Form 34: consent to research on human materials (as used by the National Biobank of Korea) | KR | ko | Statutory form; Korean Copyright Act Art. 7 excludes laws and rules | yes |
| `jp-amed-model-explanation-text` | AMED — model wording for research explanation documents (data sharing) | JP | ja | Reproduction permitted with attribution; commercial use requires AMED approval | fetch-only |
| `tw-mohw-biobank-consent-template` | Taiwan MOHW — 人體生物資料庫參與者同意書參考格式 (biobank participant consent reference template, DOCX attachment of dep.mohw.gov.tw/DOMA/cp-3133-12827-106.html) | TW | zh | Taiwan Open Government Data Licence v1 (attribution required) | yes |

Sources are credited to their publishers; nothing here is legal advice, and the documents are
used only as examples of consent language for retrieval research.
