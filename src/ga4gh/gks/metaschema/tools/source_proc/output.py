"""JSON Schema output helpers for source schema processing."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ga4gh.gks.metaschema.tools.source_proc.graph import (
    class_is_abstract,
    get_concrete_class_refs,
)

if TYPE_CHECKING:
    from ga4gh.gks.metaschema.tools.source_proc.processor import YamlSchemaProcessor


REF_RE = re.compile(r":ref:`(.*?)(\s?<.*>)?`")
LINK_RE = re.compile(r"`(.*?)\s?\<(.*)\>`_")


def scrub_rst_markup(string: str) -> str:
    """Remove RST-only markup from schema descriptions.

    :param string: Description text that may contain RST roles or links.
    :return: Plain text safe for JSON Schema descriptions.
    """
    string = REF_RE.sub(r"\g<1>", string)
    string = LINK_RE.sub(r"[\g<1>](\g<2>)", string)
    return string.replace("\n", " ")


def clean_for_js(processor: YamlSchemaProcessor) -> None:
    """Remove MSP-only metadata and expand abstract refs for JSON Schema output.

    :param processor: Owning schema processor.
    """
    processor.for_js.pop("namespaces", None)
    processor.for_js.pop("strict", None)
    processor.for_js.pop("enforce_ordered", None)
    processor.for_js.pop("imports", None)
    abstract_class_removals: list[str] = []
    for schema_class, schema_definition in processor.for_js.get(
        processor.schema_def_keyword, {}
    ).items():
        if _clean_schema_definition_for_js(processor, schema_class, schema_definition):
            abstract_class_removals.append(schema_class)

    for schema_class in abstract_class_removals:
        processor.for_js[processor.schema_def_keyword].pop(schema_class)


def _clean_schema_definition_for_js(
    processor: YamlSchemaProcessor,
    schema_class: str,
    schema_definition: dict[str, Any],
) -> bool:
    """Clean one class definition for JSON Schema output.

    :param processor: Owning schema processor.
    :param schema_class: Class name being cleaned.
    :param schema_definition: JS output definition updated in place.
    :return: ``True`` when an empty abstract definition should be removed.
    """
    schema_definition.pop("inherits", None)
    schema_definition.pop("protectedClassOf", None)
    if class_is_abstract(processor, schema_class):
        _clean_abstract_definition_for_js(processor, schema_definition)
        if not any(key in schema_definition for key in ("oneOf", "allOf", "$ref")):
            return True

    _scrub_schema_definition_descriptions(processor, schema_definition)
    return False


def _clean_abstract_definition_for_js(
    processor: YamlSchemaProcessor, schema_definition: dict[str, Any]
) -> None:
    """Remove abstract-only metadata and expand refs for one JS definition.

    :param processor: Owning schema processor.
    :param schema_definition: Abstract JS output definition updated in place.
    """
    schema_definition.pop("heritableProperties", None)
    schema_definition.pop("heritableRequired", None)
    schema_definition.pop("ga4gh", None)
    schema_definition.pop("header_level", None)
    expand_abstract_refs(processor, schema_definition)


def _scrub_schema_definition_descriptions(
    processor: YamlSchemaProcessor, schema_definition: dict[str, Any]
) -> None:
    """Remove RST markup from a JS definition and its properties.

    :param processor: Owning schema processor.
    :param schema_definition: JS output definition updated in place.
    """
    if "description" in schema_definition:
        schema_definition["description"] = scrub_rst_markup(
            schema_definition["description"]
        )
    if "properties" not in schema_definition:
        return

    for property_definition in schema_definition["properties"].values():
        if "description" in property_definition:
            property_definition["description"] = scrub_rst_markup(
                property_definition["description"]
            )
        expand_abstract_refs(processor, property_definition)


def expand_abstract_refs(
    processor: YamlSchemaProcessor, js_obj: dict[str, Any]
) -> None:
    """Replace abstract class refs with concrete descendant refs.

    :param processor: Owning schema processor.
    :param js_obj: JSON Schema node updated in place.
    """
    if "$ref" in js_obj:
        descendants = get_concrete_class_refs(processor, js_obj["$ref"])
        if descendants != {js_obj["$ref"]}:
            js_obj.pop("$ref")
            js_obj["oneOf"] = build_ref_list(descendants)
        return

    if "oneOf" in js_obj:
        descendants: set[str] = set()
        inlined: list[dict[str, Any]] = []
        for ref in js_obj["oneOf"]:
            if "$ref" not in ref:
                inlined.append(ref)
                continue
            descendants.update(get_concrete_class_refs(processor, ref["$ref"]))
        js_obj["oneOf"] = build_ref_list(descendants) + inlined
        return

    if js_obj.get("type", "") == "array":
        expand_abstract_refs(processor, js_obj["items"])


def build_ref_list(cls_urls: set[str]) -> list[dict[str, str]]:
    """Build a sorted JSON Schema ``$ref`` list.

    :param cls_urls: Class reference URLs.
    :return: Sorted list of ``{"$ref": url}`` mappings.
    """
    return [{"$ref": url} for url in sorted(cls_urls)]
