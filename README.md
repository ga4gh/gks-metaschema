# gks-metaschema

Tools and scripts for parsing GA4GH Genomic Knowledge Standards (GKS) metaschemas.
The GKS Metaschema Processor (MSP) converts
[JSON Schema Version 2020-12](https://json-schema.org/draft/2020-12/schema) in YAML to
reStructuredText (RST) and JSON files.

Currently used in:

* [GKS-Core](https://github.com/ga4gh/gks-core)
* [VRS](https://github.com/ga4gh/vrs)
* [VA-Spec](https://github.com/ga4gh/va-spec/)
* [Cat-VRS](https://github.com/ga4gh/cat-vrs)

## Installing for development

### Prerequisites

* Python 3.12: We recommend using [pyenv](https://github.com/pyenv/pyenv).

### Installation Steps

Fork the repo at <https://github.com/ga4gh/gks-metaschema>, and initialize a development
environment.

    git clone git@github.com:YOUR_GITHUB_ID/gks-metaschema.git
    cd gks-metaschema
    make devready
    source venv/3.12/bin/activate

Install `prek`:

    prek install

Check style with `ruff`:

    python3 -m ruff format . && python3 -m ruff check --fix .

### Testing

To run the tests:

    make test

## Documentation

The documentation is built with MkDocs and is configured for Read the Docs.
Serve it locally from an activated development environment with:

    mkdocs serve
