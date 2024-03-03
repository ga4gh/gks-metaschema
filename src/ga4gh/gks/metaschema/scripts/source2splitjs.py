#!/usr/bin/env python3

import pathlib
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("infile", type=argparse.FileType('r'))
parser.add_argument("outdir", type=pathlib.Path)
args = parser.parse_args()
p = YamlSchemaProcessor(args.infile)
p.split_defs_to_js(fp=args.outdir)
