"""Schema path and ref helpers for source schema processing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import yaml

if TYPE_CHECKING:
    from ga4gh.gks.metaschema.tools.source_proc.processor import YamlSchemaProcessor


DEFS_REF_RE = re.compile(r"#/(\$defs|definitions)/.*")


def _is_local_protected_class(processor: YamlSchemaProcessor, schema_class: str) -> bool:
    """Return whether a local class declares ``protectedClassOf``.

    :param processor: Owning schema processor.
    :param schema_class: Local class name to inspect.
    :return: ``True`` when the source definition declares ``protectedClassOf``.
    """
    return "protectedClassOf" in processor.raw_defs[schema_class]


def load_schema(schema_fp: Path) -> dict[str, object]:
    """Load a source YAML schema file.

    :param schema_fp: Path to the source YAML schema.
    :return: Parsed schema mapping.
    """
    with schema_fp.open(encoding="utf-8") as file_handle:
        return yaml.load(file_handle, Loader=yaml.SafeLoader)


def normalize_local_ref_paths(processor: YamlSchemaProcessor, obj: object) -> object:
    """Normalize local definition refs in a schema object.

    :param processor: Owning schema processor.
    :param obj: Schema node to inspect recursively.
    :return: ``obj`` after local ``$ref`` paths are normalized.
    :raises ValueError: If a ``$ref`` is not a local definitions reference.
    """
    if isinstance(obj, list):
        return [normalize_local_ref_paths(processor, element) for element in obj]

    if not isinstance(obj, dict):
        return obj

    for key, value in obj.items():
        if isinstance(value, (dict, list)):
            obj[key] = normalize_local_ref_paths(processor, value)
        elif isinstance(value, str) and key == "$ref":
            obj[key] = normalize_local_ref_path(processor, value)

    return obj


def normalize_local_ref_path(processor: YamlSchemaProcessor, ref: str) -> str:
    """Normalize one local definition ref path.

    :param processor: Owning schema processor.
    :param ref: Local ``$ref`` value.
    :return: Ref path using this schema's definition keyword.
    :raises ValueError: If ``ref`` is not a local definitions reference.
    """
    match = DEFS_REF_RE.match(ref)
    if match is None:
        msg = f'Expected local "$ref" definition path, got {ref}.'
        raise ValueError(msg)

    if match.group(1) == processor.schema_def_keyword:
        return ref

    return re.sub(re.escape(match.group(1)), processor.schema_def_keyword, ref)


def resolve_curie(processor: YamlSchemaProcessor, curie: str) -> str:
    """Resolve a configured ``$refCurie`` into a concrete reference URL.

    :param processor: Owning schema processor.
    :param curie: CURIE value using a configured namespace alias.
    :return: Concrete reference URL.
    """
    namespace, identifier = curie.split(":")
    return processor.namespaces[namespace] + identifier


def resolve_property_tree_refs(processor: YamlSchemaProcessor, raw_node: Any, processed_node: Any) -> None:
    """Resolve refs inside a raw/processed property tree pair.

    Example:
        A source node containing ``{"$refCurie": "vrs:Allele"}`` updates the
        matching processed node to ``{"$ref": "/ga4gh/schema/vrs/.../Allele"}``.
        Imported local refs such as ``{"$ref": "#/$defs/Thing"}`` are also
        rewritten to split-artifact-relative JSON paths when needed.

    :param processor: Owning schema processor.
    :param raw_node: Source schema node.
    :param processed_node: Processed schema node rewritten in place.
    :raises ValueError: If an imported processor is missing its root schema path.

    """
    if isinstance(raw_node, dict):
        for key, value in raw_node.items():
            if key.endswith("Curie"):
                new_key = key[:-5]
                processed_node[new_key] = resolve_curie(processor, value)
                del processed_node[key]
            elif key == "$ref" and value.startswith("#/") and processor.imported:
                if processor.root_schema_fp is None:
                    msg = "Imported schema processor is missing a root schema path."
                    raise ValueError(msg)

                rel_root = processor.schema_fp.parent.relative_to(processor.root_schema_fp.parent, walk_up=True)
                schema_stem = processor.schema_fp.stem.split("-")[0]
                processed_node[key] = str(rel_root / f"{schema_stem}.json{value}")
            else:
                resolve_property_tree_refs(processor, value, processed_node[key])
        return

    if isinstance(raw_node, list):
        for raw_item, processed_item in zip(raw_node, processed_node, strict=True):
            resolve_property_tree_refs(processor, raw_item, processed_item)


def get_class_uri(processor: YamlSchemaProcessor, schema_class: str, mode: str) -> str:
    """Return the absolute URI for a generated class artifact.

    Example:
        For a class exported under ``/ga4gh/schema/vrs/2.2.0/json/Allele``, this
        returns the full ``https://w3id.org/...`` URI built from the source
        schema ``$id`` host and the generated class path.

    :param processor: Owning schema processor.
    :param schema_class: Class name to resolve.
    :param mode: Output mode, either ``json`` or ``yaml``.
    :return: Absolute class URI.

    """
    abs_path = get_class_abs_path(processor, schema_class, mode)
    parsed_url = urlparse(processor.id)
    return f"{parsed_url.scheme}://{parsed_url.netloc}{abs_path}"


def get_class_abs_path(processor: YamlSchemaProcessor, schema_class: str, mode: str) -> str:
    """Return the absolute URL path for a generated class artifact.

    Example:
        ``get_class_abs_path(processor, "Allele", "json")`` returns a path like
        ``/ga4gh/schema/vrs/2.2.0/json/Allele``. Protected classes use the
        containing class name in the generated path.

    :param processor: Owning schema processor.
    :param schema_class: Class name to resolve.
    :param mode: Output mode, either ``json`` or ``yaml``.
    :return: Absolute URL path without scheme or host.
    :raises ValueError: If ``mode`` is not supported.

    """
    if mode == "json":
        export_key = processor.json_key
    elif mode == "yaml":
        export_key = processor.yaml_key
    else:
        msg = "mode must be json or yaml"
        raise ValueError(msg)

    if _is_local_protected_class(processor, schema_class):
        containing_class = processor.raw_defs[schema_class]["protectedClassOf"]
        class_ref = f"{containing_class}#/{processor.schema_def_keyword}/{schema_class}"
    else:
        class_ref = schema_class

    parsed_id_path = urlparse(processor.id).path
    return str(Path(parsed_id_path).parent.joinpath(export_key, class_ref))
