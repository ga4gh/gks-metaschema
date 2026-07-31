# Build and Review

From the product's `schema/` directory, run:

```shell
make all
```

The build updates configured source URL versions, generates JSON Schema and RST
artifacts, and checks for hard-coded versioned references. Review the result:

* Source YAML should contain the intended local model change.
* Generated JSON Schema should contain inherited and local properties, plus
  concrete `$ref` URLs rather than `$refCurie`.
* Generated JSON Schema and RST should not contain `{version}`.
* Generated files should reflect the source change.
