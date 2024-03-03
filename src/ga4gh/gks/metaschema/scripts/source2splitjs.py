#!/usr/bin/env python3

import pathlib
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("infile")
args = parser.parse_args()
p = YamlSchemaProcessor(pathlib.Path(args.infile))
p.split_defs_to_js()
