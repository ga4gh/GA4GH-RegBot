\# GA4GH-RegBot: Compliance Assistant



\*\*Status:\*\* Proposal Stage for GSoC 2026



GA4GH-RegBot is an LLM-powered tool designed to help researchers map their consent forms against GA4GH regulatory frameworks. It uses RAG (Retrieval-Augmented Generation) to flag compliance gaps automatically.



\## Quick Start (5 minutes)



```bash

git clone https://github.com/ga4gh/GA4GH-RegBot.git

cd GA4GH-RegBot

python -m venv venv

venv\\Scripts\\activate  # Windows

source venv/bin/activate  # Mac/Linux

pip install -r requirements.txt

copy .env.example .env  # Windows

cp .env.example .env  # Mac/Linux

\# Edit .env with your OpenAI API key

python src/main.py



