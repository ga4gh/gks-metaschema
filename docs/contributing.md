# Contributing

MSP changes can affect both schema processing and generated artifacts across
multiple GKS products. Keep changes focused, preserve documented output
behavior, and add coverage for changed behavior.

## Local Workflow

1. Create and activate the Python 3.12 development environment with
   `make devready`.
2. Install the repository hooks with `prek install`.
3. Make a focused change and update the relevant documentation.
4. Run `make test` and `python3 -m ruff check .`.
5. Review generated output when changing source processing, reference handling,
   or release preparation.

## Source and Generated Files

Source YAML files ending in `-source.yaml` are hand-edited. JSON Schema and RST
files are generated artifacts and should be regenerated through the product
`make all` workflow rather than edited by hand.

`metaschema.yaml` owns product versions, imports, and namespaces. Do not add
those sections to source YAML files. See [Metaschema
Configuration](metaschema-config.md) for the complete rules.

## Python Changes

Use type annotations for function parameters and return values. Add Sphinx-style
docstrings to public and private functions. Include an example only when it
clarifies non-obvious inputs or output.

Keep modules and functions focused. Add inline comments only where the reason
for a decision is not evident from the code. Raise explicit exceptions with
actionable messages instead of relying on assertions in production code.

## Tests

Place tests near the behavior they cover and use YAML fixtures where schema
structure is relevant. Prefer small fixtures that represent real product
layouts, including nested source directories when needed. Avoid generated test
artifacts unless the test is specifically verifying generated output.

When changing public behavior, add or update tests for success and important
failure cases. When adding a new exception, update the function docstring's
`:raises:` section.
