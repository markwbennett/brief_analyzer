# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Run Commands
- Install dependencies: `pipenv install`
- Run with single file: `pipenv run python eyecite_extractor.py document.txt`
- Run with multiple files: `pipenv run python eyecite_extractor.py file1.txt file2.txt`
- JSON output: `pipenv run python eyecite_extractor.py file.txt --json`
- HTML output: `pipenv run python eyecite_extractor.py file.txt --html`
- Save output: `pipenv run python eyecite_extractor.py file.txt --output results.json`

## Code Style Guidelines
- Python version: 3.13
- Clear docstrings for all functions
- Use consistent exception handling with specific error messages
- Follow PEP 8 conventions (4-space indentation, 79 char line limit)
- Import order: standard library → third-party → local modules
- Use type hints where appropriate
- Variables/functions use snake_case
- Classes use PascalCase
- Constants use UPPER_SNAKE_CASE
- Use PathLib for file operations instead of os.path when possible