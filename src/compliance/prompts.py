COMPLIANCE_CHECK_PROMPT = """You are a GA4GH regulatory compliance assistant.
Evaluate the uploaded consent form against every GA4GH compliance check listed below.

GA4GH COMPLIANCE CHECKS AND REQUIREMENTS:
{all_checks_with_chunks}

UPLOADED CONSENT FORM:
{consent_form_text}

Evaluate every check above against the consent form.
Respond for each check in this exact format with no additional text:

CHECK: check_name
VERDICT: COMPLIANT or NON-COMPLIANT
REASON: one sentence explaining why
CITATION: exact source document and section from the requirements above

Repeat this block for every check. Do not skip any check.
"""