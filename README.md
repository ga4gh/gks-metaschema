# gks-metaschema

Tools and scripts for parsing the GA4GH Genomic Knowledge Standards (GKS) metaschemas.
The metaschema processor (MSP) converts
[JSON Schema Version 2020-12](json-schema.org/draft/2020-12/schema) in YAML to
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

Set up `pre-commit` hooks:

    pre-commit install

### Testing

To run the tests:

    make test

## Usage

### File Hierarchy

The metaschema processor expects the following hierarchy:

    ├── docs
    │   ├── source
    │   |   ├── ...
    │   ├── Makefile
    ├── schema
    │   ├──gks_schema
    │   |   ├── metaschema.yaml
    │   |   ├── gks-schema-source.yaml
    │   |   ├── Makefile
    │   |   ├── prune.mk
    │   ├── Makefile

* `docs`: [Sphinx](https://www.sphinx-doc.org/en/master/index.html) documentation
    directory. **Must** be named `docs`.
  * `source`: Directory containing documentation written in reStructuredText and Sphinx
    configuration. **Must** be named `source`.
  * `Makefile`: Commands to create the reStructuredText files.
    This file should not change across GKS projects.
* `schema`: Schema build directory. Can also contain submodules for other GKS product
  schemas.
  * `gks_schema`: Schema directory for GKS product. The directory name should reflect
    the product, e.g. `vrs`.
    * `metaschema.yaml`: Central configuration for release versions, imports, and
          namespaces.
    * `gks-schema-source.yaml`: Source document for the JSON Schema 2020-12. The file name
          should reflect the standard, e.g. `vrs-source.yaml`. The  file name **must** end
          with `-source.yaml`.
    * `Makefile`: Commands to create the reStructuredText and JSON files.
          This file should not change across GKS projects.
    * `prune.mk`: Cleanup of files in `def` and `json` directories based on source document.
          This file should not change across GKS projects.
  * `Makefile`: Commands to create the reStructuredText and JSON files.

### Contributing to the schema

To create the corresponding `def` (reStructuredText) and `json` files after making
changes to the source document, from the _schema_ directory:

    make all

### Updating schema versions for releases

Use `schema/<product>/metaschema.yaml` to define release metadata once per product.
Source files under that product directory, including nested directories such as
`schema/va-spec/base`, all use that configuration.

    versions:
      va-spec: 1.1.0
    imports:
      vrs: ../vrs/vrs-source.yaml
      cat-vrs: ../cat-vrs/catvrs-source.yaml
    namespaces:
      vrs: /ga4gh/schema/vrs/{version}/json/
      cat-vrs: /ga4gh/schema/cat-vrs/{version}/json/

In practice, release users usually update only `metaschema.yaml`, then run the
standard schema build:

    make all

To prepare a release, run `gks-release-prep` from the root of the product
repository being released. The product
name is inferred from the repository directory name; for example, a checkout
directory named `va-spec` uses `schema/va-spec/metaschema.yaml`. The immediate
upstream product is inferred from the single submodule entry in `.gitmodules`.
Products without an upstream submodule, such as `gks-core`, omit
`--upstream-branch`. If the existing `.gitmodules` branch is already correct,
use `--use-current-upstream-branch` to confirm that choice. If the upstream
submodule should not be changed, use `--skip-upstream`.

    gks-release-prep --version 1.1.0 --upstream-branch 1.2.0-ballot.2026-07

This command is intended for local release prep because it mutates the working
tree, updates `.gitmodules`, updates the submodule from the confirmed remote
branch, and checks out the selected submodule tag. It prints the product,
schema path, submodule branch/tag, and build steps as it runs. It does not
stage or commit changes. Dirty product or submodule worktrees produce warnings;
use `--fail-on-dirty` for strict behavior.

To validate the same inputs without changing files, add `--validate`.

MSP applies those values while processing source YAML and writes concrete
versions into generated `json` and `def` artifacts.

See [Metaschema Configuration](docs/metaschema-config.md) for config rules and
generated output behavior. See [Release Prep](docs/release-prep.md) for the
local release workflow.

The file structure will now look like:

    ├── schema
    │   ├──gks_schema
    │   |   ├── metaschema.yaml
    |   |   ├── def
    │   |   |   ├── ...
    |   |   ├── json
    │   |   |   ├── ...
    │   |   ├── gks-schema-source.yaml
    │   |   ├── Makefile
    │   |   ├── prune.mk
    │   ├── Makefile

### Contributing to the docs

GKS specification documentation is written in reStructuredText and located in
`docs/source`.

To build documentation locally, you must install [entr](https://eradman.com/entrproject/):

    brew install entr

Then from the _docs_ directory:

    make clean watch &

Then, open `docs/build/html/index.html`. The above make command should build docs when
the source changes.

> **NOTE**: Some types of changes require recleaning and building.
