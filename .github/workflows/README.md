# GitHub Actions Workflows

This directory contains automated workflows for GA4GH-RegBot.

## Workflows

### 1. Lint and Code Quality (lint.yml)

**Trigger:** Every push and pull request

**What it does:**
- Runs all pre-commit hooks
- Checks code formatting (Black)
- Lints with Ruff
- Type checks with mypy
- Validates imports with isort

**On Failure:**
- Comments on PR with helpful message
- Shows which checks failed
- Suggests running \pre-commit run --all-files\ locally

---

### 2. Tests (tests.yml)

**Trigger:** Every push and pull request

**What it does:**
- Runs Python tests with pytest
- Tests on multiple Python versions (3.8, 3.9, 3.10, 3.11, 3.12)
- Generates coverage reports
- Uploads to Codecov

**On Failure:**
- Comments on PR with test results
- Shows which Python versions failed
- Provides coverage information

---

### 3. Auto-format (format.yml)

**Trigger:** Pull requests only

**What it does:**
- Runs Black formatter
- Sorts imports with isort
- Fixes linting issues with Ruff
- Auto-commits fixes to PR branch
- Comments on PR when fixes applied

**Note:** This is non-blocking - PRs can still be reviewed even if auto-format runs

---

## Local Testing

To test workflows locally before pushing:

\\\ash
# Install act (runs GitHub Actions locally)
choco install act-cli  # Windows
brew install act       # Mac
apt-get install act    # Linux

# Run a specific workflow
act -j lint

# Run all workflows
act
\\\

## Troubleshooting

### Workflow won't trigger
- Check branch protection rules
- Verify workflow file is valid YAML
- Check file is in correct location: \.github/workflows/\

### Tests fail but pass locally
- Make sure Python version matches
- Check that all dependencies are in requirements.txt
- Run \pip install -e .\ for local testing

### Auto-fix not committing changes
- Check GitHub token has write permissions
- Verify branch is not protected
- Check git configuration in workflow

## Adding New Workflows

To add a new workflow:
1. Create new file in \.github/workflows/\
2. Use YAML syntax (see examples above)
3. Push to GitHub to test
4. Verify in Actions tab

## Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Pre-commit with Actions](https://pre-commit.com/#github-actions)
- [Act - Run GitHub Actions Locally](https://github.com/nektos/act)
