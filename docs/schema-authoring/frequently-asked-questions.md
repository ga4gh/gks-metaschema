# Frequently Asked Questions

## Should I edit files in `json/` or `def/`?

No. They are complete generated output from source YAML. Update the source and
run `make all`.

## Do I repeat an upstream version in my product?

No. MSP reads an imported product's version from that product's
`metaschema.yaml`. Your product declares only its own version.

## Do I copy every upstream import and namespace?

No. Declare only the aliases used directly by this product's source YAML.

## Do imports and namespaces always appear together?

No. Use `imports` when MSP needs an upstream definition. Use `namespaces` when
an alias must render to a generated `$ref` URL. An alias can use one or both,
depending on how the source YAML uses it.

## Where does `metaschema.yaml` belong?

Place one `metaschema.yaml` at `schema/<product>/`. Nested source directories
use that product-level configuration and must not contain another one.

## Can a source `$ref` contain a versioned GA4GH URL?

No. Use `$refCurie` with a configured namespace alias. MSP renders the concrete
versioned `$ref` URL in generated JSON Schema.

## What version should a source YAML `$id` use?

Use the concrete local product version in `metaschema.yaml`. MSP reports an
error when the two versions do not match.
