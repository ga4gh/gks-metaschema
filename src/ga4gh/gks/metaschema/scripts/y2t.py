#!/usr/bin/env python3
"""Generate RST definition artifacts from processed GKS source YAML."""

import sys
from pathlib import Path
from typing import TextIO

from jinja2 import Environment, FileSystemLoader

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

templates_dir = Path(__file__).resolve().parents[4] / "templates"
env = Environment(loader=FileSystemLoader(templates_dir))

# Mapping to corresponding hex color code and code for maturity status
MATURITY_MAPPING: dict[str, tuple[str, str]] = {
    "draft": ("D3D3D3", "D"),
    "trial use": ("FFFF99", "TU"),
    "normative": ("B6D7A8", "N"),
    "deprecated": ("EA9999", "X"),
}

# Mapping to corresponding code for ordered property in arrays
ORDERED_MAPPING: dict[bool, str] = {True: "&#8595;", False: "&#8942;"}


def resolve_type(class_property_definition: dict) -> str:
    """Resolve a class property definition to a rendered type.

    :param class_property_definition: Property type definition.
    :return: Rendered type, or ``_Not Specified_`` when undetermined.
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
    """Resolve class property cardinality from a YAML definition.

    :param class_property_name: Class property name.
    :param class_property_attributes: Class property attributes.
    :param class_definition: Class definition.
    :return: Cardinality string.
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
    """Get the nearest ancestor class with rendered attributes.

    :param class_name: Class name.
    :param proc: Schema processor that owns the class.
    :return: Ancestor class name.
    """
    if proc.class_is_passthrough(class_name):
        raw_def, proc = proc.get_class_definition(class_name, raw=True)
        ancestor = raw_def.get("inherits")
        return get_ancestor_with_attributes(ancestor, proc)
    return class_name


def add_ga4gh_digest(class_definition: dict, stream: TextIO) -> None:
    """Add a GA4GH digest table when digest metadata is present.

    :param class_definition: Model definition.
    :param stream: Writable RST file stream.
    """
    ga4gh_digest = class_definition.get("ga4gh", {})
    if ga4gh_digest:
        print(
            f"""
**GA4GH Digest**

.. list-table::
    :class: clean-wrap
    :header-rows: 1
    :align: left
    :widths: auto

    *  - Prefix
       - Inherent

    *  - {ga4gh_digest.get("prefix", None)}
       - {str(ga4gh_digest.get("inherent", []))}\n""",
            file=stream,
        )


def resolve_flags(class_property_attributes: dict) -> str:
    """Render badges for maturity and ordered-property flags.

    :param class_property_attributes: Property attributes for a class.
    :return: Rendered flag badges.
    """
    flags = ""
    maturity = class_property_attributes.get("maturity")

    if maturity is not None:
        background_color, maturity_code = MATURITY_MAPPING.get(maturity, (None, None))
        if background_color and maturity_code:
            title = f"{maturity.title()} Maturity Level"
            flags += f"""
                        .. raw:: html

                            <span style="background-color: #{background_color}; color: black; padding: 2px 6px; border: 1px solid black; border-radius: 3px; font-weight: bold; display: inline-block; margin-bottom: 5px;" title="{title}">{maturity_code}</span>"""

    ordered = class_property_attributes.get("ordered")
    ordered_code = ORDERED_MAPPING.get(ordered, None)

    if ordered_code is not None:
        title = "Ordered" if ordered else "Unordered"
        if not flags:
            flags += """
                        .. raw:: html\n"""

        flags += f"""
                            <span style="background-color: #B2DFEE; color: black; padding: 2px 6px; border: 1px solid black; border-radius: 3px; font-weight: bold; display: inline-block; margin-bottom: 5px;" title="{title}">{ordered_code}</span>"""
    return flags


def _write_maturity_notice(class_definition: dict, stream: TextIO) -> None:
    """Write the maturity notice for a class, if one applies.

    :param class_definition: Processed class definition.
    :param stream: Writable RST file stream.
    """
    maturity = class_definition.get("maturity", "")
    template = env.get_template("maturity")
    if maturity == "draft":
        print(
            template.render(info="warning", maturity_level="draft", modifier="significantly"),
            file=stream,
        )
        print(file=stream)
    elif maturity == "trial use":
        print(
            template.render(info="note", maturity_level="trial use", modifier=""),
            file=stream,
        )
        print(file=stream)


def _get_information_model_property_key(
    class_name: str, class_definition: dict, proc_schema: YamlSchemaProcessor
) -> str | None:
    """Get the property map key used for an information model table.

    :param class_name: Class name being rendered.
    :param class_definition: Processed class definition.
    :param proc_schema: Schema processor that owns the class.
    :return: ``heritableProperties`` or ``properties``; ``None`` for primitive
        classes that do not render an information model.
    :raises ValueError: If a non-primitive class has no property map.
    """
    if "heritableProperties" in class_definition:
        return "heritableProperties"
    if "properties" in class_definition:
        return "properties"
    if proc_schema.class_is_primitive(class_name):
        return None

    msg = f"{class_name} is missing heritableProperties or properties."
    raise ValueError(msg)


def _get_inheritance_text(class_name: str, proc_schema: YamlSchemaProcessor) -> str:
    """Get RST text describing inherited attributes.

    :param class_name: Class name being rendered.
    :param proc_schema: Schema processor that owns the class.
    :return: Inheritance sentence, or an empty string when the class has no parent.
    """
    ancestor = proc_schema.raw_defs[class_name].get("inherits")
    if not ancestor:
        return ""

    ancestor = get_ancestor_with_attributes(ancestor, proc_schema)
    return f"Some {class_name} attributes are inherited from :ref:`{ancestor}`.\n"


def _write_information_model_header(inheritance: str, stream: TextIO) -> None:
    """Write the information model table header.

    :param inheritance: Inheritance sentence to print before the table.
    :param stream: Writable RST file stream.
    """
    print("\n**Information Model**", file=stream)
    print(
        f"""
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
      - Description""",
        file=stream,
    )


def _format_property_row(class_property_name: str, class_property_attributes: dict, class_definition: dict) -> str:
    """Format one information model property row.

    :param class_property_name: Property name.
    :param class_property_attributes: Processed property attributes.
    :param class_definition: Processed class definition.
    :return: RST list-table row.
    """
    class_definition_formatted = f"""\
   *  - {class_property_name}
      - {resolve_flags(class_property_attributes)}
      - {resolve_type(class_property_attributes)}
      - {resolve_cardinality(class_property_name, class_property_attributes, class_definition)}
      - {class_property_attributes.get("description", "")}"""
    return "\n".join(line.rstrip() for line in class_definition_formatted.splitlines())


def _write_information_model(
    class_name: str, class_definition: dict, property_key: str, proc_schema: YamlSchemaProcessor, stream: TextIO
) -> None:
    """Write an information model table for one class.

    :param class_name: Class name being rendered.
    :param class_definition: Processed class definition.
    :param property_key: Property map key to render.
    :param proc_schema: Schema processor that owns the class.
    :param stream: Writable RST file stream.
    """
    inheritance = _get_inheritance_text(class_name, proc_schema)
    add_ga4gh_digest(class_definition, stream)
    _write_information_model_header(inheritance, stream)

    for class_property_name, class_property_attributes in class_definition[property_key].items():
        print(_format_property_row(class_property_name, class_property_attributes, class_definition), file=stream)


def _write_class_rst(class_name: str, class_definition: dict, proc_schema: YamlSchemaProcessor) -> None:
    """Write the RST artifact for one class.

    :param class_name: Class name being rendered.
    :param class_definition: Processed class definition.
    :param proc_schema: Schema processor that owns the class.
    :raises ValueError: If a non-primitive class has no property map.
    """
    with (proc_schema.def_fp / (class_name + ".rst")).open("w", encoding="utf-8") as stream:
        _write_maturity_notice(class_definition, stream)
        print("**Computational Definition**\n", file=stream)
        print(class_definition["description"], file=stream)

        if proc_schema.class_is_passthrough(class_name):
            return

        property_key = _get_information_model_property_key(class_name, class_definition, proc_schema)
        if property_key is None:
            return

        _write_information_model(class_name, class_definition, property_key, proc_schema, stream)


def main(proc_schema: YamlSchemaProcessor) -> None:
    """Generate one RST file for each class in a schema.

    :param proc_schema: Schema processor containing definitions to render.
    """
    for class_name, class_definition in proc_schema.defs.items():
        _write_class_rst(class_name, class_definition, proc_schema)


def cli() -> None:
    """Parse CLI arguments and generate RST definitions from a source schema."""
    source_file = Path(sys.argv[1])
    p = YamlSchemaProcessor(source_file)
    p.def_fp.mkdir(exist_ok=True)
    if p.defs is None:
        raise SystemExit(0)
    main(p)


if __name__ == "__main__":
    cli()
