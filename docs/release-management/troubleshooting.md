# Troubleshooting

## Missing `metaschema.yaml`

Each product must have one configuration file at
`schema/<product>/metaschema.yaml`. MSP uses that file for all source YAML below
the product directory. Do not create nested `metaschema.yaml` files.

## Source `$id` Version Does Not Match

The concrete version in a product source `$id` must match the product version
in `metaschema.yaml`. Update the product version through `metaschema.yaml`,
then run the schema build or `source2updated` to update source URL segments.

## Hard-Coded Versioned `$ref`

`source2updated --disallow-versioned-refs` rejects versioned GA4GH `$ref` URLs
in source YAML. Replace them with a `$refCurie` and define the required alias in
the product's `metaschema.yaml` `namespaces` section. Add an `imports` entry
when MSP also needs the upstream definition.

## Unresolved `$refCurie` or `{version}` in Generated Output

Generated JSON Schema must contain concrete `$ref` URLs and versions. Generated
JSON Schema and RST must not contain `{version}`. Check that the current product
declares the aliases it uses and that each namespace resolves to a configured
version. If the source configuration is valid and generated output still has a
CURIE or template, report it as an MSP bug with a minimal source fixture.

## Release Prep Cannot Find a Submodule, Branch, or Tag

Run `gks-release-prep` from the product repository root. For downstream
products, ensure `.gitmodules` has one immediate upstream entry and the
submodule is available remotely. Pass `--upstream-branch` to select a branch,
or `--use-current-upstream-branch` to confirm the branch already configured in
`.gitmodules`.

Use `--validate` to check the product, submodule, branch, and tag without
changing files. See [Release Preparation](release-prep.md) for the full local
workflow.

## Build Fails After a Schema Change

Read the first error reported by `make all`; later errors can be consequences of
the first one. Confirm that source YAML indentation and references are valid,
then check whether the source `$id`, configured version, imports, and namespaces
agree. See [How It Works](../schema-authoring/index.md) for the build and review
workflow.

## Still Stuck

Record the command you ran, the first complete error message, the product and
source file involved, and the relevant `metaschema.yaml` entries. This gives a
schema maintainer or MSP developer enough context to reproduce the problem.
