#!/usr/bin/env python3

import pathlib
import sys

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor


def cli():
    source_file = pathlib.Path(sys.argv[1])
    p = YamlSchemaProcessor(source_file)
    p.js_yaml_dump(sys.stdout)


if __name__ == "__main__":
    cli()
