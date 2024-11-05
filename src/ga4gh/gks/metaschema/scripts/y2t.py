#!/usr/bin/env python3
"""convert input .yaml to .rst artifacts"""

from io import TextIOWrapper
import os
import sys
import pathlib
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor


# Mapping to corresponding hex color code and code for maturity status
MATURITY_MAPPING: dict[str, tuple[str, str]] = {
    "draft": ("D3D3D3", "D"),
    "trial_use": ("FFFF99", "TU"),
    "normative": ("B6D7A8", "N"),
    "deprecated": ("EA9999", "X")
}

# Mapping to corresponding code for ordered property in arrays
ORDERED_MAPPING: dict[bool, str] = {
    True: "OL",
    False: "UL"
}


def resolve_type(class_property_definition):
    if 'type' in class_property_definition:
        if class_property_definition['type'] == 'array':
            return resolve_type(class_property_definition['items'])
        return class_property_definition['type']
    elif '$ref' in class_property_definition:
        ref = class_property_definition['$ref']
        identifier = ref.split('/')[-1]
        return f':ref:`{identifier}`'
    elif '$refCurie' in class_property_definition:
        ref = class_property_definition['$refCurie']
        identifier = ref.split('/')[-1]
        return f':ref:`{identifier}`'
    elif 'oneOf' in class_property_definition or 'anyOf' in class_property_definition:
        kw = 'oneOf'
        if 'anyOf' in class_property_definition:
            kw = 'anyOf'
        deprecated_types = class_property_definition.get('deprecated', list())
        resolved_deprecated = list()
        resolved_active = list()
        for property_type in class_property_definition[kw]:
            resolved_type = resolve_type(property_type)
            if property_type in deprecated_types:
                resolved_deprecated.append(resolved_type + f' (deprecated)')
            else:
                resolved_active.append(resolved_type)
        return ' | '.join(resolved_active + resolved_deprecated)
    else:
        return "_Not Specified_"


def resolve_cardinality(class_property_name, class_property_attributes, class_definition):
    """Resolve class property cardinality from yaml definition"""
    if class_property_name in class_definition.get('required', []):
        min_count = '1'
    elif class_property_name in class_definition.get('heritableRequired', []):
        min_count = '1'
    else:
        min_count = '0'
    if class_property_attributes.get('type') == 'array':
        max_count = class_property_attributes.get('maxItems', 'm')
        min_count = class_property_attributes.get('minItems', 0)
    else:
        max_count = '1'
    return f'{min_count}..{max_count}'


def get_ancestor_with_attributes(class_name, proc):
    if proc.class_is_passthrough(class_name):
        raw_def, proc = proc.get_local_or_inherited_class(class_name, raw=True)
        ancestor = raw_def.get('inherits')
        return get_ancestor_with_attributes(ancestor, proc)
    return class_name



def add_ga4gh_digest(class_definition: dict, f: TextIOWrapper) -> None:
    """Add GA4GH Digest table

    Will only include this table if both ``prefix`` and ``keys`` are provided

    :param class_definition: Model definition
    :param f: RST file
    """
    ga4gh_digest = class_definition.get("ga4ghDigest") or {}
    if ga4gh_digest:
        ga4gh_prefix = ga4gh_digest.get("prefix") or "None"
        print(f"""
**GA4GH Digest**

.. list-table::
    :class: clean-wrap
    :header-rows: 1
    :align: left
    :widths: auto

    *  - Prefix
       - Keys

    *  - {ga4gh_prefix}
       - {str(ga4gh_digest.get("keys") or [])}\n""", file=f)


def resolve_flags(class_property_attributes: dict) -> str:
    """Add badges for flags (maturity and ordered property)

    :param class_property_attributes: Property attributes for a class
    :return: Output for flag badges
    """
    flags = ""
    maturity = class_property_attributes.get("maturity")

    if maturity is not None:
        background_color, maturity_code = MATURITY_MAPPING.get(maturity, (None, None))
        if background_color and maturity_code:
            flags += f"""
                        .. raw:: html

                            <span style="background-color: #{background_color}; color: black; padding: 2px 6px; border: 1px solid black; border-radius: 3px; font-weight: bold; display: block; margin-bottom: 5px;">{maturity_code}</span>"""

    ordered = class_property_attributes.get("ordered")
    ordered_code = ORDERED_MAPPING.get(ordered, None)

    if ordered_code is not None:
        if not flags:
            flags += """
                        .. raw:: html\n"""

        flags += f"""
                            <span style="background-color: #B2DFEE; color: black; padding: 2px 6px; border: 1px solid black; border-radius: 3px; font-weight: bold; display: block; margin-bottom: 5px;">{ordered_code}</span>"""
    return flags


def main(proc_schema):
    for class_name, class_definition in proc_schema.defs.items():
        with open(proc_schema.def_fp / (class_name + '.rst'), "w") as f:
            maturity = class_definition.get('maturity', '')
            if maturity == 'draft':
                print("""
.. warning:: This data class is at a **draft** maturity level and may change
    significantly in future releases. Maturity levels are described in 
    the :ref:`maturity-model`.
                      
                    """, file=f)
            elif maturity == 'trial use':
                print("""
.. note:: This data class is at a **trial use** maturity level and may change
    in future releases. Maturity levels are described in the :ref:`maturity-model`.
                      
                    """, file=f)
            print("**Computational Definition**\n", file=f)
            print(class_definition['description'], file=f)
            if proc_schema.class_is_passthrough(class_name):
                continue
            if 'heritableProperties' in class_definition:
                p = 'heritableProperties'
            elif 'properties' in class_definition:
                p = 'properties'
            elif proc_schema.class_is_primitive(class_name):
                continue
            else:
                raise ValueError(class_name, class_definition)
            ancestor = proc_schema.raw_defs[class_name].get('inherits')
            if ancestor:
                ancestor = get_ancestor_with_attributes(ancestor, proc_schema)
                inheritance = f"Some {class_name} attributes are inherited from :ref:`{ancestor}`.\n"
            else:
                inheritance = ""

            add_ga4gh_digest(class_definition, f)

            print("\n**Information Model**", file=f)
            print(f"""
{inheritance}
.. list-table::
   :class: clean-wrap
   :header-rows: 1
   :align: left
   :widths: auto

   *  - Field
      - Flags
      - Type
      - Limits
      - Description""", file=f)
            for class_property_name, class_property_attributes in class_definition[p].items():
                print(f"""\
   *  - {class_property_name}
      - {resolve_flags(class_property_attributes)}
      - {resolve_type(class_property_attributes)}
      - {resolve_cardinality(class_property_name, class_property_attributes, class_definition)}
      - {class_property_attributes.get('description', '')}""", file=f)

def cli():
    source_file = pathlib.Path(sys.argv[1])
    p = YamlSchemaProcessor(source_file)
    os.makedirs(p.def_fp, exist_ok=True)
    if p.defs is None:
        exit(0)
    main(p)

if __name__ == "__main__":
    cli()