#!/usr/bin/env python3

import pathlib
import sys
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

source_file = pathlib.Path(sys.argv[1])
p = YamlSchemaProcessor(source_file)
p.split_defs_to_js()
