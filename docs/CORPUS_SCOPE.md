# Regulatory Corpus Scope and Completion Rule

## Status

As of 10 August 2026, corpus manifest v0.6 is **scope-complete for the GSoC release**:

- 85 documents and 8,081 indexed chunks;
- 83 reproducible publisher fetch targets;
- 73 primary-source documents, 10 explicitly labelled reference translations, and
  2 contributor summaries;
- nine normalized scopes: `GA4GH`, `INTL`, `EU`, `SG`, `CN`, `TW`, `KR`, `JP`, and `HK`.

“Scope-complete” means the finite criteria below are satisfied. It does not mean every law,
guideline, amendment, language version, or country in the world is represented, and it is
not a claim of legal completeness.

## Inclusion criteria

A source is included when it is materially relevant to at least one of these review axes:

1. genomic or health-data governance and sharing;
2. consent, secondary use, withdrawal, or participant engagement;
3. ethics review, human-subject research, or return of results;
4. biobanks, human genetic resources, genetic testing, or discrimination; or
5. privacy, security, data access, or cross-border transfer in the above contexts.

The preferred source is a current official or publisher-authenticated full text with a
stable, reproducible URL. Each automated target must pass minimum-length and required-phrase
checks before being written. Superseded versions and landing-page summaries are not added
when a current normative full text is available. A non-authoritative English translation is
retained only when it materially improves retrieval and is labelled `translation`; it never
replaces the legally effective authentic-language text.

## Coverage and stopping decisions

| Scope | Completion boundary |
|-------|---------------------|
| GA4GH / REWS | Current, directly relevant Support Ready or explicitly approved policies and tools with stable full text, including all six Consent Toolkit clause sets. Active/in-progress work, meeting material, roadmaps, news, surveys, organizational codes, and purely technical standards are excluded. |
| International / EU | Core WHO, OECD, UNESCO and Council of Europe genomic/health-data and bioethics instruments, plus operative EU law and EDPB guidance directly needed for consent, research, secondary use, governance and transfers. General privacy, AI, open-science, obsolete duplicate, and non-redistributable texts are excluded. |
| Singapore | PDPA, HBRA and its research/tissue regulations, plus the enacted Health Information Act. |
| China | HGR, PIPL, Data Security and Biosecurity frameworks; human-research ethics; and the principal export-assessment, standard-contract and cross-border/network-data mechanisms. |
| Taiwan | Biobank, personal-data and human-subject-research statutes cover the five review axes; no extra general medical law is needed for this release. |
| South Korea | Bioethics and PIPA Acts plus their enforcement decrees. KLRI English texts are reference translations; current Korean consolidations remain legally controlling. |
| Japan | APPI, medical/biological research ethics and guidance, medical-data secondary use, and genomic-medicine promotion. The former contributor summary is excluded from the index because full primary texts now cover it. |
| Hong Kong | PDPO, section 33 transfer guidance/model clauses, and the eHealth Code of Practice. |

The two remaining summaries are intentionally visible as `content_type: summary`; they are
context aids, not substitutes for cited law. Retrieval and the UI badge them accordingly.

## Reopening rule

Add or replace material only when at least one of these events occurs:

- an indexed law, policy, or guidance receives a substantive new version;
- GA4GH publishes a newly approved normative REWS product within the review axes;
- an upstream URL breaks or a publisher makes a better authenticated full text available;
- mentor review of the gold set identifies a concrete retrieval gap; or
- the project explicitly expands to another jurisdiction.

Otherwise, adding adjacent documents merely to increase the count is out of scope. The next
release task is independent mentor review of the gold set, followed by a benchmark rerun on
this 85-document snapshot; that review is intentionally not claimed as complete here.
