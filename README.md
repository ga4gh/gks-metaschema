# gks-metaschema

This repository houses tools and scripts for parsing the GKS standards
metaschemas.

## Getting started

- Clone or fork this repo.
- Create a virtual environment: `python -m venv venv`
- Activate the virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install -e .[dev]`
- Run the test suite: `pytest`
- Create an environment variable `PROJECT_ROOT_DIR` and make its value
  the absolute path to this repository.
- Set up the `pre-commit` hook: `cp ./scripts/pre-commit ./.git/hooks/`