#!/usr/bin/env python3

import json
import sys

import yaml


def cli():
    yaml_schema = yaml.load(sys.stdin, Loader=yaml.SafeLoader)
    json.dump(yaml_schema, sys.stdout, indent=3)


if __name__ == "__main__":
    cli()
