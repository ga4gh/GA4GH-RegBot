from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv

load_dotenv()
llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY")
)


def explain_missing_clause(clause_text, research_doc):

    prompt = f"""
You are a policy compliance assistant.

Framework Requirement:
{clause_text}

Research Document:
{research_doc}

Explain briefly why the research document does not satisfy this requirement.
Explain ONLY why the research document does not satisfy this clause.
Do not introduce new requirements not present in the clause.
Keep the explanation short.
"""

    response = llm.invoke(prompt)

    return response.content