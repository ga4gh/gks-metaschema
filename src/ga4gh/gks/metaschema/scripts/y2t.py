#!/usr/bin/env python3
"""convert input .yaml to .rst artifacts"""

import os
import pathlib
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

templates_dir = Path(__file__).resolve().parents[4] / "templates"
env = Environment(loader=FileSystemLoader(templates_dir))



def resolve_type(class_property_definition: dict) -> str:
    """Resolves a class definition to a concrete type.

    :param class_property_definition: type definition, "_Not Specified_" if undetermined
    """
    if "type" in class_property_definition:
        if class_property_definition["type"] == "array":
            return resolve_type(class_property_definition["items"])
        return class_property_definition["type"]
    elif "$ref" in class_property_definition:
        ref = class_property_definition["$ref"]
        identifier = ref.split("/")[-1]
        return f":ref:`{identifier}`"
    elif "$refCurie" in class_property_definition:
        ref = class_property_definition["$refCurie"]
        identifier = ref.split("/")[-1]
        return f":ref:`{identifier}`"
    elif "oneOf" in class_property_definition or "anyOf" in class_property_definition:
        kw = "oneOf"
        if "anyOf" in class_property_definition:
            kw = "anyOf"
        deprecated_types = class_property_definition.get("deprecated", [])
        resolved_deprecated = []
        resolved_active = []
        for property_type in class_property_definition[kw]:
            resolved_type = resolve_type(property_type)
            if property_type in deprecated_types:
                resolved_deprecated.append(resolved_type + " (deprecated)")
            else:
                resolved_active.append(resolved_type)
        return " | ".join(resolved_active + resolved_deprecated)
    else:
        return "_Not Specified_"


def resolve_cardinality(class_property_name: str, class_property_attributes: dict, class_definition: dict) -> str:
    """Resolves class property cardinality from YAML definition.

    :param class_property_name: class property name
    :param class_property_attributes: class property attributes
    :param class_definition: class definition
    """
    if class_property_name in class_definition.get("required", []):
        min_count = "1"
    elif class_property_name in class_definition.get("heritableRequired", []):
        min_count = "1"
    else:
        min_count = "0"
    if class_property_attributes.get("type") == "array":
        max_count = class_property_attributes.get("maxItems", "m")
        min_count = class_property_attributes.get("minItems", 0)
    else:
        max_count = "1"
    return f"{min_count}..{max_count}"


def get_ancestor_with_attributes(class_name: str, proc: YamlSchemaProcessor) -> str:
    """Returns the ancestor class of the class name

    :param class_name: class name
    :param proc: yaml schema processor
    """
    if proc.class_is_passthrough(class_name):
        raw_def, proc = proc.get_local_or_inherited_class(class_name, raw=True)
        ancestor = raw_def.get("inherits")
        return get_ancestor_with_attributes(ancestor, proc)
    return class_name


def main(proc_schema: YamlSchemaProcessor) -> None:
    """
    Generates the .rst file for each of the classes in the schema

    :param proc_schema: schema processor object
    """
    for class_name, class_definition in proc_schema.defs.items():
        with open(proc_schema.def_fp / (class_name + ".rst"), "w") as f:
            maturity = class_definition.get("maturity", "")
            if maturity == "draft":
                template = env.get_template("maturity")
                print(
                    template.render(
                        info="warning",
                        maturity_level="draft",
                        modifier="significantly"
                    ),
                    file=f,
                )
            elif maturity == "trial use":
                print(
                    template.render(
                        info="note",
                        maturity_level="trial use",
                        modifier=""
                    ),
                    file=f,
                )
            print("**Computational Definition**\n", file=f)
            print(class_definition["description"], file=f)
            if proc_schema.class_is_passthrough(class_name):
                continue
            if "heritableProperties" in class_definition:
                p = "heritableProperties"
            elif "properties" in class_definition:
                p = "properties"
            elif proc_schema.class_is_primitive(class_name):
                continue
            else:
                raise ValueError(class_name, class_definition)
            ancestor = proc_schema.raw_defs[class_name].get("inherits")
            if ancestor:
                ancestor = get_ancestor_with_attributes(ancestor, proc_schema)
                inheritance = f"Some {class_name} attributes are inherited from :ref:`{ancestor}`.\n"
            else:
                inheritance = ""
            print("\n**Information Model**", file=f)
            print(
                f"""
{inheritance}
.. list-table::
   :class: clean-wrap
   :header-rows: 1
   :align: left
   :widths: auto

   *  - Field
      - Type
      - Limits
      - Description""",
                file=f,
            )
            for class_property_name, class_property_attributes in class_definition[p].items():
                print(
                    f"""\
   *  - {class_property_name}
      - {resolve_type(class_property_attributes)}
      - {resolve_cardinality(class_property_name, class_property_attributes, class_definition)}
      - {class_property_attributes.get('description', '')}""",
                    file=f,
                )


def cli():
    source_file = pathlib.Path(sys.argv[1])
    p = YamlSchemaProcessor(source_file)
    os.makedirs(p.def_fp, exist_ok=True)
    if p.defs is None:
        exit(0)
    main(p)


if __name__ == "__main__":
    cli()
