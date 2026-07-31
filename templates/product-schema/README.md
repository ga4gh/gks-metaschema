# Product Schema Build Template

Copy `Makefile` and `prune.mk` together into a directory containing one or more
`*-source.yaml` files. The template runs MSP source-processing commands,
generates JSON Schema and RST artifacts, and removes output for models no longer
exported by the source files.

Copy `schema/Makefile` to a product's `schema/` directory. It finds source
areas and runs their Makefiles, allowing product-level `make all` and
`make clean` commands.
