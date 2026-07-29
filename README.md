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
`schema/va-spec/base`, all use that configuration. The allowed top-level keys are
`versions`, `imports`, and `namespaces`:

    versions:
      va-spec: 1.1.0
    imports:
      vrs: ../vrs/vrs-source.yaml
      cat-vrs: ../cat-vrs/catvrs-source.yaml
    namespaces:
      vrs: /ga4gh/schema/vrs/{version}/json/
      cat-vrs: /ga4gh/schema/cat-vrs/{version}/json/

In practice, this means release users usually update only `metaschema.yaml`, then
run `make all`. MSP applies those values while processing source YAML and writes
concrete versions into generated `json` and `def` artifacts.

Terminology used in this section:

* `product`: One GKS schema package under `schema/<product>`, such as `vrs` or
  `va-spec`.
* `source YAML`: A hand-edited schema file ending in `-source.yaml`.
* `generated artifacts`: Files created from source YAML, such as split JSON Schema
  files under `json/` and reStructuredText files under `def/`.
* `local`: Values defined by the current product's `metaschema.yaml`.
* `imported` or `upstream`: Values loaded from another product's
  `metaschema.yaml` through the current product's `imports`.
* `downstream`: A product that imports another product.
* `namespace alias`: The short name used in `$refCurie` values, such as `vrs` in
  `$refCurie: vrs:Allele`.
* `hard-coded versioned $ref`: A `$ref` that includes a concrete schema version
  directly instead of using a namespace alias.

How MSP uses `metaschema.yaml`:

* It validates that source `$id` values already use the configured concrete
  product version.
* It loads imports and namespaces from `metaschema.yaml` instead of from source
  YAML files.
* It renders `{version}` in namespace values using the local product version or
  the imported product's own version.
* It rejects namespace templates that use `{version}` when no matching local or
  imported product version is available.
* It rejects namespace URLs with hard-coded versions that do not match the
  configured local or imported product version.
* It writes concrete versioned URLs to generated artifacts. Generated files
  should not contain `{version}`.

Keep the following rules in mind:

* A product should have exactly one metaschema configuration file
  (`metaschema.yaml`). Nested metaschema configuration files below
  `schema/<product>` are rejected.
* Source YAML files should not define `versions`, `imports`, or `namespaces`.
  MSP logs a warning and removes these values.
* `imports` and `namespaces` should include aliases directly used by that product's
  source YAML files. Downstream products should not copy upstream aliases
  unless the downstream source files use those aliases directly.
* Upstream `versions` do not need to be repeated downstream. `namespaces` may use
  `{version}`, which MSP renders from the local `versions` entry or the imported
  product's own `metaschema.yaml`. If a namespace uses a concrete version
  instead, that version must already match the configured version.
* Product source `$id` values must use the concrete version from
  `metaschema.yaml`; MSP raises an error if the `$id` is stale.
* Source YAML files should use namespace-based refs such as `$refCurie`,
  not hard-coded versioned `$ref` URLs.

Example source `$id`:

    $id: "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/va-spec-source.yaml"

To update versioned URL segments in source YAML files and regenerate artifacts,
run the standard schema build:

    make all

The shared schema Makefile runs `source2updated --disallow-versioned-refs` before
generating artifacts. This updates stale configured version references and
fails when a configured spec still uses a hard-coded versioned `$ref`. For
release validation or CI, `source2updated --check --disallow-versioned-refs`
can be used to fail without editing files:

    source2updated --check --disallow-versioned-refs schema

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
