# Contributing

This guide is for contributors changing MSP's Python code, tests, or developer
documentation.

## Local Workflow

1. Create and activate the Python 3.12 development environment with
   `make devready`.
2. Install the repository hooks with `prek install`.
3. Run `make test` and `python3 -m ruff check .`.
4. Review generated output when changing source processing, reference handling,
   or release preparation.

## Python Changes

Use type annotations for function parameters and return values. Add Sphinx-style
docstrings to public and private functions. Include an example only when it
clarifies non-obvious inputs or output.

Keep modules and functions focused. Add inline comments only where the reason
for a decision is not evident from the code. Raise explicit exceptions with
actionable messages instead of relying on assertions in production code.

## Tests

Place tests near the behavior they cover. Use YAML fixtures when schema
structure is relevant, and prefer small fixtures that represent real product
layouts. Avoid generated test artifacts unless a test verifies generated output.

When changing public behavior, add or update tests for success and important
failure cases. When adding a new exception, update the function docstring's
`:raises:` section.

## Documentation Changes

Update the relevant guide when a behavior change affects schema authors or
release users.
