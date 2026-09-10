#!/usr/bin/env python3
"""convert input .yaml to .rst artifacts"""

import os
import pathlib
import sys
from io import TextIOWrapper
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ga4gh.gkm.metaschema.tools.source_proc import YamlSchemaProcessor

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


def add_ga4gh_digest(class_definition: dict, f: TextIOWrapper) -> None:
    """Add GA4GH Digest table

    Will only include this table if both ``prefix`` and ``inherent`` are provided

    :param class_definition: Model definition
    :param f: RST file
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
            file=f,
        )


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


def describe_composition_member(member: dict) -> str:
    """Human-readable RST for a single allOf/oneOf/anyOf member schema."""
    if any(key in member for key in ("$ref", "$refCurie", "oneOf", "anyOf")):
        return resolve_type(member)
    if "properties" in member:
        fields = ", ".join(f"``{name}``" for name in member["properties"])
        if fields:
            return f"an object constraining {fields}"
    return "an object with additional constraints"


def resolve_composition(class_definition: dict) -> str:
    """RST describing an allOf/oneOf/anyOf composed class.

    Returns an empty string when the class is not composed. Used to give
    composed classes (which have no property table of their own) a useful
    Information Model rather than a blank section.
    """
    for keyword, label in (("oneOf", "one of"), ("anyOf", "any of")):
        if keyword in class_definition:
            members = class_definition[keyword]
            lines = [f"This class must match **{label}** the following:\n"]
            lines += [f"* {describe_composition_member(m)}" for m in members]
            return "\n".join(lines) + "\n"
    return ""


def _class_registry(proc: YamlSchemaProcessor) -> dict:
    """Map class name -> processed definition, across this schema and its imports.

    Cached on the processor. Used to resolve the base class(es) an allOf-composed
    class refines, so their (already-flattened) properties can be overlaid.
    """
    cached = getattr(proc, "_y2t_registry", None)
    if cached is not None:
        return cached
    reg: dict = {}

    def collect(p: YamlSchemaProcessor, seen: set) -> None:
        if id(p) in seen:
            return
        seen.add(id(p))
        for name, defn in p.processed_schema.get(p.schema_def_keyword, {}).items():
            reg.setdefault(name, defn)
        for imported in p.imports.values():
            collect(imported, seen)

    collect(proc, set())
    proc._y2t_registry = reg
    return reg


def _ref_class_name(member: dict) -> str | None:
    """Extract the referenced class name from a $ref (path) or $refCurie member."""
    ref = member.get("$ref") or member.get("$refCurie")
    if not ref:
        return None
    frag = ref.split("#")[-1]  # drop any JSON-pointer fragment
    name = frag.rsplit("/", 1)[-1]  # last path segment
    return name.rsplit(":", 1)[-1] or None  # strip a CURIE namespace prefix


def flatten_allof(class_definition: dict, proc: YamlSchemaProcessor):
    """Flatten an allOf-composed class to its effective property set.

    Overlays each referenced base class's properties (in order) with the local
    ``properties`` refinements. Returns (effective_properties, refined_names,
    sorted_required, base_class_names). Refined/added names win but keep the
    position they hold in the base (superclass-first ordering).
    """
    registry = _class_registry(proc)
    effective: dict = {}
    refined: set = set()
    required: set = set()
    bases: list = []
    for member in class_definition.get("allOf", []):
        base_name = _ref_class_name(member)
        if base_name and base_name in registry:
            base = registry[base_name]
            bases.append(base_name)
            for name, attribs in base.get("properties", {}).items():
                effective.setdefault(name, attribs)
            required.update(base.get("required", []))
        if "properties" in member:
            for name, attribs in member["properties"].items():
                # overlay the refinement on the base definition so inherited
                # facets (e.g. type/items) survive alongside the new constraints
                effective[name] = {**effective.get(name, {}), **attribs}
                refined.add(name)
            required.update(member.get("required", []))
    # fold in any properties declared directly on the class as well
    for name, attribs in class_definition.get("properties", {}).items():
        effective[name] = {**effective.get(name, {}), **attribs}
        refined.add(name)
    required.update(class_definition.get("required", []))
    return effective, refined, sorted(required), bases


def render_information_model(f, properties: dict, required: list, note: str = "", refined=frozenset()) -> None:
    """Render an Information Model list-table for a property set.

    Shared by ordinary classes and allOf-composed classes. ``refined`` names are
    flagged so a reader can see which fields a recipe/profile constrained.
    """
    if not properties:
        return
    print(
        f"""
{note}
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
        file=f,
    )
    synthetic = {"required": required}
    for name, attribs in properties.items():
        field = f"{name} *(refined)*" if name in refined else name
        row = f"""\
   *  - {field}
      - {resolve_flags(attribs)}
      - {resolve_type(attribs)}
      - {resolve_cardinality(name, attribs, synthetic)}
      - {attribs.get("description", "")}"""
        print("\n".join(line.rstrip() for line in row.splitlines()), file=f)


def main(proc_schema: YamlSchemaProcessor) -> None:
    """
    Generates the .rst file for each of the classes in the schema

    :param proc_schema: schema processor object
    """
    for class_name, class_definition in proc_schema.defs.items():
        with open(proc_schema.def_fp / (class_name + ".rst"), "w") as f:
            maturity = class_definition.get("maturity", "")
            template = env.get_template("maturity")
            if maturity == "draft":
                print(
                    template.render(info="warning", maturity_level="draft", modifier="significantly"),
                    file=f,
                )
                print(file=f)
            elif maturity == "trial use":
                print(
                    template.render(info="note", maturity_level="trial use", modifier=""),
                    file=f,
                )
                print(file=f)
            if proc_schema.class_is_abstract(class_name):
                print(
                    "**Abstract Class** — not instantiated directly; concrete subclasses inherit its attributes.\n",
                    file=f,
                )
            print("**Computational Definition**\n", file=f)
            print(class_definition["description"], file=f)
            if proc_schema.class_is_passthrough(class_name):
                composition = resolve_composition(class_definition)
                if composition:
                    print("\n**Information Model**\n", file=f)
                    print(composition, file=f)
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

            add_ga4gh_digest(class_definition, f)

            print("\n**Information Model**", file=f)
            if "allOf" in class_definition:
                # allOf = refinement: show the effective (flattened) property
                # table — base class properties overlaid with the local
                # refinements — like any other class, marking refined fields.
                effective, refined, required, bases = flatten_allof(class_definition, proc_schema)
                if effective:
                    note = ""
                    if bases:
                        note = "This class refines " + ", ".join(f":ref:`{b}`" for b in bases) + ".\n"
                    render_information_model(f, effective, required, note, refined)
                else:
                    composition = resolve_composition(class_definition)
                    if composition:
                        print("\n" + composition, file=f)
            else:
                render_information_model(f, class_definition[p], class_definition.get("required", []), inheritance)
            # oneOf/anyOf unions: list the alternative member schemas.
            composition = resolve_composition(class_definition)
            if composition:
                print("\n" + composition, file=f)

        # Normalize generated RST: strip trailing whitespace on every line and
        # end each file with a single newline, so output matches what pre-commit
        # produces and re-running the generator never dirties the working tree.
        for rst_file in proc_schema.def_fp.glob("*.rst"):
            text = rst_file.read_text()
            normalized = "\n".join(line.rstrip() for line in text.splitlines())
            rst_file.write_text(normalized.rstrip("\n") + "\n")


def cli():
    source_file = pathlib.Path(sys.argv[1])
    p = YamlSchemaProcessor(source_file)
    os.makedirs(p.def_fp, exist_ok=True)
    if p.defs is None:
        exit(0)
    main(p)


if __name__ == "__main__":
    cli()
