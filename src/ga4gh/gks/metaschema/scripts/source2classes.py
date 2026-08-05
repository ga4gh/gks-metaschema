"""Print public class names from a processed schema"""

import argparse
from pathlib import Path

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor


def main(proc: YamlSchemaProcessor) -> None:
    """Print public class names from a processed schema.

    :param proc: Processor containing the schema classes to list.
    """
    for cls in proc.processed_classes:
        if proc.class_is_protected(cls):
            continue
        print(cls)


def _parse_args() -> argparse.Namespace:
    """Parse class listing CLI arguments.

    :return: Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("infile")
    return parser.parse_args()


def cli() -> None:
    """Parse CLI arguments and print source schema class names."""
    args = _parse_args()
    p = YamlSchemaProcessor(Path(args.infile))
    main(p)


if __name__ == "__main__":
    cli()
