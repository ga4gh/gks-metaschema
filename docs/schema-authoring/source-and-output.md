# Source YAML and Generated Output

Source YAML defines local model content. MSP resolves inheritance and imports to
produce complete JSON Schema and RST artifacts for publication.

## Simple Product Layout

A simple product has one source YAML file at the product level:

```text
schema/
  <product>/
    metaschema.yaml          Product version, imports, and namespaces
    example-source.yaml      JSON Schema source with local definitions
    Makefile                 Builds generated artifacts
    prune.mk                 Removes obsolete generated artifacts
    json/                    Generated JSON Schema
    def/                     Generated RST
```

## Nested Product Layout

Products can also organize source YAML into nested areas. All source files use
the same product-level `metaschema.yaml`.

```text
schema/
  <product>/
    metaschema.yaml          Product version, imports, and namespaces
    models/
      example-model-source.yaml
      Makefile               Builds generated artifacts
      prune.mk               Removes obsolete generated artifacts
      json/                  Generated JSON Schema
      def/                   Generated RST
    profiles/
      example-profile-source.yaml
      Makefile               Builds generated artifacts
      prune.mk               Removes obsolete generated artifacts
      json/                  Generated JSON Schema
      def/                   Generated RST
```

The exact source directory and file names differ by product. Each source area
has its own `Makefile`, `prune.mk`, and generated `json/` and `def/` directories.
The important rule is that there is one `metaschema.yaml` at
`schema/<product>/`, not one per nested source directory.

Use the repository's [Product Build Template](product-build-template.md) when
creating a new source area.

## Editable and Generated Files

Files ending in `-source.yaml` are the editable JSON Schema source of truth.
They describe models, local properties, descriptions, examples, inheritance,
and relationships to other models. They do not need to repeat properties that a
model receives through inheritance.

Do not edit generated files under `json/` or `def/` directly. They are complete
generated output from source YAML; update the source and run `make all`.
