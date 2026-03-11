# Environment Setup Guide

This guide explains how to set up environment variables for GA4GH-RegBot.

## Quick Start

1. **Copy the template:**
   \\\ash
   cp .env.example .env
   \\\

2. **Fill in your values:**
   - Open \.env\ in a text editor
   - Add your actual API keys and settings
   - Save the file

3. **Verify setup:**
   \\\ash
   python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('API Key:', os.getenv('OPENAI_API_KEY', 'NOT SET'))"
   \\\

## Required Variables

### OpenAI Configuration (Required)

**OPENAI_API_KEY**
- **What:** Your OpenAI API key for GPT access
- **How to get:** 
  1. Go to https://platform.openai.com/api-keys
  2. Click "Create new secret key"
  3. Copy the key immediately (you won't see it again)
  4. Paste into \.env\
- **Example:** \sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\
- **Security:** Keep this secret! Never share or commit to Git

**OPENAI_MODEL**
- **What:** Which OpenAI model to use
- **Options:** \gpt-3.5-turbo\, \gpt-4\, \gpt-4-turbo-preview\
- **Default:** \gpt-3.5-turbo\ (cheapest, fast)

## Common Issues & Solutions

### Issue: "OPENAI_API_KEY not found"
**Solution:**
1. Make sure you created \.env\ file (not \.env.example\)
2. Make sure you filled in the actual API key
3. Verify \.env\ is in the project root directory

### Issue: "Module 'python-dotenv' not found"
**Solution:**
\\\ash
pip install python-dotenv
\\\

## Security Best Practices

**🔒 DO:**
- ✅ Keep \.env\ in \.gitignore\
- ✅ Use placeholder values in \.env.example\
- ✅ Rotate API keys regularly

**🚫 DON'T:**
- ❌ Commit \.env\ to Git
- ❌ Share API keys in Slack or email
- ❌ Log sensitive values

## Loading Environment Variables in Code

\\\python
from dotenv import load_dotenv
import os

# Load from .env file
load_dotenv()

# Access variables
api_key = os.getenv('OPENAI_API_KEY')
model = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')  # with default
\\\

For complete guide, see [ENV_SETUP.md](ENV_SETUP.md)
