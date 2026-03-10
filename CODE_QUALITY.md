# Code Quality Guidelines

This project uses automated code quality tools to maintain consistent code standards.

## Tools Used

### Black
**Purpose:** Automatic code formatter
- Enforces consistent code style
- Line length: 100 characters
- Run: \lack src/\

### Ruff
**Purpose:** Fast Python linter
- Checks PEP 8 compliance
- Catches common errors
- Fixes issues automatically
- Run: \uff check --fix src/\

### isort
**Purpose:** Sorts and organizes imports
- Groups imports: stdlib, third-party, local
- Compatibility: Works with Black
- Run: \isort src/\

### mypy
**Purpose:** Static type checker
- Catches type errors before runtime
- Helps document code intent
- Run: \mypy src/\

## Installation

### First Time Setup

\\\ash
pip install pre-commit
pre-commit install
\\\

The hooks will now run automatically before each commit.

### Without Git Hooks (Manual)

\\\ash
pre-commit run --all-files
black src/
ruff check --fix src/
isort src/
mypy src/
\\\

## Common Issues & Solutions

### Pre-commit blocks my commit
Follow the suggestions and fix issues, then commit again

### Module not found in mypy
Add to \.pre-commit-config.yaml\:
\\\yaml
additional_dependencies: ['types-package-name']
\\\

### Black and Ruff conflict
Already configured in \pyproject.toml\ to be compatible
