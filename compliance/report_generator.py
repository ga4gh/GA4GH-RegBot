from compliance.explainer import explain_missing_clause

def generate_report(present, missing, research_text):

    total = len(present) + len(missing)
    score = (len(present) / total) * 100 if total > 0 else 0

    print("\nCompliance Report")
    print("------------------")

    print(f"\nTotal Clauses Checked: {total}")
    print(f"Clauses Covered: {len(present)}")
    print(f"Clauses Missing: {len(missing)}")
    print(f"Compliance Score: {score:.2f}%")

    print("\nMissing Requirements:\n")

    for clause in missing:

        section = clause.metadata.get("section", "N/A")
        title = clause.metadata.get("section_title", "N/A")
        subsection = clause.metadata.get("subsection", "N/A")

        print("Section:", section)
        print("Title:", title)

        if subsection:
            print("Subsection:", subsection)

        print("\nRequirement:")
        print(clause.page_content)

        # Call the LLM explainer
        explanation = explain_missing_clause(
            clause.page_content,
            research_text
        )

        print("\nExplanation:")
        print(explanation)

        print("-" * 60)