#!/usr/bin/env python3
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("infile")

def main(proc):
    for cls in proc.processed_classes:
        print(cls)

if __name__ == '__main__':
    args = parser.parse_args()
    p = YamlSchemaProcessor(Path(args.infile))
    main(proc)
