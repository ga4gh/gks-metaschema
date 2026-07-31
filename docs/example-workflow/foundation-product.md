
# Foundation Product

`foundation-product` has no dependencies.

## Layout

```text
foundation-product/
  schema/
    Makefile
    foundation-product/
      metaschema.yaml
      foundation-source.yaml
      Makefile
      prune.mk
```

Each source YAML build directory needs these two files:
[Makefile](../assets/product-schema/Makefile) and
[prune.mk](../assets/product-schema/prune.mk). Preview the files and copy both
templates together as described in the [Product Build Template](../schema-authoring/product-build-template.md)
guide.

## Configuration and Source

`foundation-product/schema/foundation-product/metaschema.yaml` defines only the local
product version:

```yaml
versions:
  foundation-product: 1.0.0
```

Its source YAML defines a local model. The `$id` has the same concrete version
as `metaschema.yaml`.

```yaml
$schema: "https://json-schema.org/draft/2020-12/schema"
$id: "https://w3id.org/ga4gh/schema/foundation-product/1.0.0/foundation-source.yaml"
title: Foundation Product
type: object
$defs:
  FoundationModel:
    type: object
    maturity: draft
    properties:
      identifier:
        type: string
```

Run the product build from `foundation-product/schema/`:

```shell
make all
```

## Layout After Build

Lines prefixed with `+` are created by `make all`.

```text
foundation-product/
  schema/
    Makefile
    foundation-product/
      metaschema.yaml
      foundation-source.yaml
      Makefile
      prune.mk
      + build/
        + foundation.classes
      + json/
        + FoundationModel
      + def/
        + FoundationModel.rst
```

## Generated JSON Schema

`make all` writes one JSON Schema artifact for each exported model. For this
product, `schema/foundation-product/json/FoundationModel` contains the local
model definition:

```json
{
   "$schema": "https://json-schema.org/draft/2020-12/schema",
   "$id": "https://w3id.org/ga4gh/schema/foundation-product/1.0.0/json/FoundationModel",
   "title": "FoundationModel",
   "type": "object",
   "maturity": "draft",
   "properties": {
      "identifier": {
         "type": "string"
      }
   }
}
```

## Release Preparation

After preparing the `foundation-product` release branch and choosing version
`1.1.0`, run the release command from the repository root:

```shell
gks-release-prep --version 1.1.0
```

The command updates the local version and source URL segments, runs the product
build, and verifies configured references. Review the resulting changes, then
commit and tag the foundation release.

## Updated Versions

Release preparation updates the configured product version, the source `$id`,
and regenerated artifact `$id` values to `1.1.0`:

```yaml
# metaschema.yaml
versions:
  foundation-product: 1.1.0

# foundation-source.yaml
$id: "https://w3id.org/ga4gh/schema/foundation-product/1.1.0/foundation-source.yaml"
```
