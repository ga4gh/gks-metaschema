
# Dependent Product

`dependent-product` has one submodule, `foundation-product`.

## Layout

```text
dependent-product/
  .gitmodules
  submodules/foundation-product/
  schema/
    Makefile
    foundation-product -> ../submodules/foundation-product/schema/foundation-product
    dependent-product/
      metaschema.yaml
      dependent-source.yaml
      Makefile
      prune.mk
```

`dependent-product` records its dependency as a Git submodule. Its `.gitmodules`
file has one entry for `foundation-product` and identifies the remote branch the
product follows. The `schema/foundation-product` symlink exposes the imported
product beside the local product schema.

```ini
[submodule "submodules/foundation-product"]
  path = submodules/foundation-product
  url = https://github.com/example/foundation-product.git
  branch = 1.0
```

## Configuration and Reference

Its `metaschema.yaml` declares the local version plus only the alias this
product uses directly:

```yaml
versions:
  dependent-product: 2.0.0
imports:
  foundation: ../foundation-product/foundation-source.yaml
namespaces:
  foundation: /ga4gh/schema/foundation-product/{version}/json/
```

`dependent-source.yaml` refers to the imported model through the configured
alias. It does not repeat `foundation-product`'s version. The `{version}` in
the `foundation` namespace resolves to `foundation-product`'s `1.0.0`, not the
dependent product's `2.0.0`.

```yaml
$schema: "https://json-schema.org/draft/2020-12/schema"
$id: "https://w3id.org/ga4gh/schema/dependent-product/2.0.0/dependent-source.yaml"
title: Dependent Product
type: object
$defs:
  DependentModel:
    type: object
    maturity: draft
    properties:
      foundation:
        $refCurie: foundation:FoundationModel
```

Run the product build from `dependent-product/schema/`:

```shell
make all
```

## Layout After Build

Lines prefixed with `+` are created by `make all`.

```text
dependent-product/
  .gitmodules
  submodules/foundation-product/
  schema/
    Makefile
    foundation-product -> ../submodules/foundation-product/schema/foundation-product
    dependent-product/
      metaschema.yaml
      dependent-source.yaml
      Makefile
      prune.mk
      + build/
        + dependent.classes
      + json/
        + DependentModel
      + def/
        + DependentModel.rst
```

## Generated JSON Schema

`make all` writes one JSON Schema artifact for each exported model. For this
example, `schema/dependent-product/json/DependentModel` contains the concrete
reference to the foundation product:

```json
{
   "$schema": "https://json-schema.org/draft/2020-12/schema",
   "$id": "https://w3id.org/ga4gh/schema/dependent-product/2.0.0/json/DependentModel",
   "title": "DependentModel",
   "type": "object",
   "maturity": "draft",
   "properties": {
      "foundation": {
         "$ref": "/ga4gh/schema/foundation-product/1.0.0/json/FoundationModel"
      }
   }
}
```

The generated artifact has a concrete `$ref` with the foundation product's
version. It does not retain the source YAML's `$refCurie` or `{version}`
template.

For the configuration rules behind this example, see
[Configuration](../schema-authoring/configuration.md) and
[References to Other Models](../schema-authoring/references.md).

## Release Preparation

Once the `foundation-product` release branch and tag are available remotely, run
release preparation from the `dependent-product` repository root. Supply the
foundation branch that the dependent product should follow:

### Use the Latest Tag on a Branch

```shell
gks-release-prep --version 2.1.0 --upstream-branch 1.1
```

This resolves the latest release tag reachable from the `1.1` foundation
branch.

### Pin a Specific Tag

To use a particular foundation release tag instead, provide both the branch and
the tag:

```shell
gks-release-prep --version 2.1.0 --upstream-branch 1.1 --upstream-tag v1.1.0
```

`--upstream-tag` expects the exact Git tag name, including `v` when present.
The tag selects the Git checkout; `metaschema.yaml` versions never include `v`.

The command updates the foundation submodule, resolves its release tag,
updates the local product version and source URLs, regenerates artifacts, and
verifies references. It does not stage, commit, tag, or push the resulting
changes.

## Updated Versions and Dependency

Release preparation moves the foundation submodule to its `1.1.0` release,
updates the dependent product to `2.1.0`, and regenerates the dependent JSON
Schema reference:

```ini
# .gitmodules
branch = 1.1
```

```yaml
# metaschema.yaml
versions:
  dependent-product: 2.1.0

# dependent-source.yaml
$id: "https://w3id.org/ga4gh/schema/dependent-product/2.1.0/dependent-source.yaml"

# json/DependentModel
$ref: "/ga4gh/schema/foundation-product/1.1.0/json/FoundationModel"
```

If the foundation branch is already correct in `.gitmodules`, use
`--use-current-upstream-branch` instead. For a particular upstream tag, add
`--upstream-tag`. See [Release Preparation](../release-management/release-prep.md)
for those options and validation mode.
