#!/usr/bin/env python3
import argparse
from pathlib import Path

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

parser = argparse.ArgumentParser()
parser.add_argument("infile")


def main(proc):
    for cls in proc.processed_classes:
        if proc.class_is_protected(cls):
            continue
        print(cls)


def cli():
    args = parser.parse_args()
    p = YamlSchemaProcessor(Path(args.infile))
    main(p)


if __name__ == "__main__":
    cli()
