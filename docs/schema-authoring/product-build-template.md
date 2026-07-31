# Product Build Template

Each directory that builds `*-source.yaml` files needs both a `Makefile` and a
`prune.mk`. The `Makefile` runs MSP commands to update source references and
generate artifacts. `prune.mk` removes generated JSON Schema and RST files for
models that are no longer exported.

Copy both the [Makefile](../assets/product-schema/Makefile) and
[prune.mk](../assets/product-schema/prune.mk) into the source area. The previews
below show the files stored in `templates/product-schema/` in this repository.

## Makefile

```makefile
--8<-- "templates/product-schema/Makefile"
```

## prune.mk

```makefile
--8<-- "templates/product-schema/prune.mk"
```
