"""Process a source YAML file with imports merged and write YAML to stdout."""

import pathlib
import sys

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor


def cli() -> None:
    """Process a source YAML file with imports merged and write YAML to stdout."""
    source_file = pathlib.Path(sys.argv[1])
    p = YamlSchemaProcessor(source_file)
    p.merge_imported_definitions()
    p.js_yaml_dump(sys.stdout)


if __name__ == "__main__":
    cli()
