# Metaschema Configuration

Use `schema/<product>/metaschema.yaml` to define release metadata once per
product. Source files under that product directory, including nested directories
such as `schema/va-spec/base`, all use that configuration.

Allowed top-level keys are:

```yaml
versions:
  va-spec: 1.1.0
imports:
  vrs: ../vrs/vrs-source.yaml
  cat-vrs: ../cat-vrs/catvrs-source.yaml
namespaces:
  vrs: /ga4gh/schema/vrs/{version}/json/
  cat-vrs: /ga4gh/schema/cat-vrs/{version}/json/
```

In practice, release users usually update only `metaschema.yaml`, then run
`make all`. MSP applies those values while processing source YAML and writes
concrete versions into generated `json` and `def` artifacts.

## Terminology

* `product`: One GKS schema package under `schema/<product>`, such as `vrs` or
  `va-spec`.
* `source YAML`: A hand-edited schema file ending in `-source.yaml`.
* `generated artifacts`: Files created from source YAML, such as split JSON
  Schema files under `json/` and reStructuredText files under `def/`.
* `local`: Values defined by the current product's `metaschema.yaml`.
* `imported` or `upstream`: Values loaded from another product's
  `metaschema.yaml` through the current product's `imports`.
* `downstream`: A product that imports another product.
* `namespace alias`: The short name used in `$refCurie` values, such as `vrs` in
  `$refCurie: vrs:Allele`.
* `hard-coded versioned $ref`: A `$ref` that includes a concrete schema version
  directly instead of using a namespace alias.

## Config Rules

* A product should have exactly one metaschema configuration file
  (`metaschema.yaml`). Nested metaschema configuration files below
  `schema/<product>` are rejected.
* Source YAML files should not define `versions`, `imports`, or `namespaces`.
  During processing, MSP warns and ignores those source-local values. During
  release updates, `source2updated` removes those sections from source files.
* `imports` and `namespaces` should include aliases directly used by that
  product's source YAML files. Downstream products should not copy upstream
  aliases unless the downstream source files use those aliases directly.
* `imports` and `namespaces` do not need to be one-to-one. Use `imports` when
  MSP must load another source schema, such as for inherited classes or imported
  definitions. Use `namespaces` when an alias must render to an output `$ref`.
  Many aliases need both, but an external `$refCurie` can use only `namespaces`
  if MSP does not need to inspect the upstream source schema.
* Upstream `versions` do not need to be repeated downstream. `namespaces` may use
  `{version}`, which MSP renders from the local `versions` entry or the imported
  product's own `metaschema.yaml`. If a namespace uses a concrete version
  instead, that version must already match the configured version.
* Product source `$id` values must use the concrete version from
  `metaschema.yaml`; MSP raises an error if the `$id` is stale.
* Source YAML files should use namespace-based refs such as `$refCurie`, not
  hard-coded versioned `$ref` URLs.

## Intended Output

Source YAML may use `$refCurie` and namespace `{version}` templates as authoring
conveniences, but generated artifacts should be fully resolved.

Expected generated output:

* JSON Schema artifacts should contain concrete `$ref` values, not `$refCurie`.
* JSON Schema and RST artifacts should not contain `{version}`.
* Source `$id` values must already contain the concrete product version from
  `metaschema.yaml`; stale or templated `$id` versions are errors.
* Commented-out YAML is ignored by hard-coded `$ref` checks.

If generated output contains `$refCurie`, `{version}`, or a stale configured
schema version, treat that as a bug unless a test fixture explicitly documents
the exception.

## Release Updates

To update versioned URL segments in source YAML files and regenerate artifacts,
run the standard schema build from the product's `schema` directory:

```shell
make all
```

The shared schema Makefile runs `source2updated --disallow-versioned-refs`
before generating artifacts. This updates stale configured version references
and fails when a configured spec still uses a hard-coded versioned `$ref`.

For release validation or CI, use check mode to fail without editing files:

```shell
source2updated --check --disallow-versioned-refs schema
```
