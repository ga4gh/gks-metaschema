# Product Build Template

Each source area that builds `*-source.yaml` files needs both a `Makefile` and a
`prune.mk`. The `Makefile` runs MSP commands to update source references and
generate artifacts. `prune.mk` removes generated JSON Schema and RST files for
models that are no longer exported. A product's `schema/` directory also needs
a Makefile that runs each source-area build.

## Schema Makefile

Copy this [schema Makefile](../assets/product-schema/schema-Makefile) to the
product's `schema/` directory. It makes `make all` and `make clean` run the
corresponding command in every source area.

```makefile
--8<-- "templates/product-schema/schema/Makefile"
```

## Source-Area Files

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
