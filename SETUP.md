\# GA4GH-RegBot: Development Setup Guide



Welcome! This guide will help you set up GA4GH-RegBot for local development and testing.



\## Prerequisites



\- \*\*Python 3.8+\*\*

\- \*\*pip\*\* (comes with Python)

\- \*\*Git\*\*



\## Quick Start (5 minutes)



```bash

\# 1. Clone the repository

git clone https://github.com/ga4gh/GA4GH-RegBot.git

cd GA4GH-RegBot



\# 2. Create a virtual environment

python -m venv venv

venv\\Scripts\\activate  # Windows



\# 3. Install dependencies

pip install -r requirements.txt



\# 4. Set up environment

copy .env.example .env



\# 5. Verify

python -c "import langchain; import chromadb; print('OK')"



