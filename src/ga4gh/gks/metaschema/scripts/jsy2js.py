"""Read YAML from stdin and write formatted JSON to stdout"""

import json
import sys

import yaml


def cli() -> None:
    """Read YAML from stdin and write formatted JSON to stdout."""
    yaml_schema = yaml.load(sys.stdin, Loader=yaml.SafeLoader)
    json.dump(yaml_schema, sys.stdout, indent=3)


if __name__ == "__main__":
    cli()
