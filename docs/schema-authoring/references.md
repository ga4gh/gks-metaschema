# References to Other Models

Use a `$refCurie`, a compact URI expression (CURIE), for a configured namespace
alias:

```yaml
$refCurie: vrs:Allele
```

Do not write a versioned GA4GH URL directly in a source `$ref`. The alias and
its version are owned by `metaschema.yaml`, which keeps a release update from
requiring many source-file edits.

Declare only the imports and namespaces used directly by the current product's
source YAML. You do not need to copy every import or namespace from upstream
products.
