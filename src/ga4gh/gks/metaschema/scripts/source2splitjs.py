#!/usr/bin/env python3
"""Write one split JSON Schema artifact per processed class.

Split output rewrites local and imported class refs to the concrete paths
generated from each processor's configured namespace.
"""

import argparse
import copy
import json
import re
from pathlib import Path

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

JsonValue = str | int | float | bool | None | dict | list
REF_FRAGMENT_RE = re.compile(r"(/\$defs|definitions)/(\w+)")


def _get_import_artifact_stems(proc: YamlSchemaProcessor) -> set[str]:
    """Get artifact stems that can refer to an imported processor.

    Example:
        An imported processor for ``model-source.yaml`` returns
        ``{"model-source", "model"}``, allowing refs such as ``model.json`` to
        match the import.

    :param proc: Imported schema processor to match against external refs.
    :return: Candidate artifact stems for generated schema paths.

    """
    source_stem = proc.schema_fp.stem
    return {source_stem, source_stem.removesuffix("-source")}


def _get_primary_exported_class(proc: YamlSchemaProcessor) -> str:
    """Get the primary exported class for an imported processor.

    Example:
        An imported processor whose only non-protected definition is
        ``CategoricalVariant`` returns ``"CategoricalVariant"``.

    :param proc: Imported schema processor to inspect.
    :return: Primary exported class name.
    :raises ValueError: If the processor does not have exactly one exported class.

    """
    exported_classes = [cls for cls in proc.defs if not proc.class_is_protected(cls)]

    if len(exported_classes) != 1:
        classes = ", ".join(sorted(exported_classes))
        msg = f"Could not infer primary exported class from {proc.schema_fp}. Exported classes: {classes}"
        raise ValueError(msg)

    return exported_classes[0]


def _find_import_processor_for_ref(
    ref: str, ref_class: str, root_proc: YamlSchemaProcessor
) -> tuple[YamlSchemaProcessor | None, str]:
    """Find the imported processor and class for an external reference.

    Example:
        ``model.json#/$defs/CategoricalVariant`` resolves by the parsed class
        name, ``CategoricalVariant``. ``model.json`` resolves by matching
        ``model`` to an imported source artifact and then using that import's
        single exported class. If the ``model`` import owns
        ``CategoricalVariant``, both inputs return
        ``(model_processor, "CategoricalVariant")``. An unmanaged external ref
        such as ``https://example.org/schema.json`` returns ``(None,
        "schema")``.

    :param ref: External reference path without a fragment.
    :param ref_class: Class name inferred from the reference path or fragment.
    :param root_proc: Root schema processor whose imports are searched.
    :return: Imported processor and resolved reference class, or ``None`` and
        the original class if no processor matches.

    """
    # Refs with fragments name the target class directly, e.g.
    # model.json#/$defs/CategoricalVariant.
    for other in root_proc.imports.values():
        if ref_class in other.defs:
            return other, ref_class

    # Fragmentless refs name the generated artifact, e.g. model.json. Match that
    # artifact stem to an import and use the import's single exported class.
    ref_stem = Path(ref).stem
    for other in root_proc.imports.values():
        if ref_stem in _get_import_artifact_stems(other):
            return other, _get_primary_exported_class(other)

    return None, ref_class


def _resolve_ref_curie(
    ref_curie: str, root_proc: YamlSchemaProcessor, mode: str
) -> str:
    """Resolve a ``$refCurie`` for split output.

    Split output should never contain ``$refCurie``. Most CURIEs are resolved
    earlier by ``YamlSchemaProcessor``; this helper handles any that survive
    through inherited or merged property data.

    :param ref_curie: CURIE reference such as ``vrs:Allele``.
    :param root_proc: Root schema processor for resolving imports and namespaces.
    :param mode: Output mode of ``json`` or ``yaml``.
    :return: Concrete ``$ref`` path.
    """
    namespace, ref_class = ref_curie.split(":", 1)
    if namespace in root_proc.imports:
        proc = root_proc.imports[namespace]
        return proc.get_class_abs_path(ref_class, mode)

    # A namespace can be enough when MSP only needs to render an external ref and
    # does not need to inspect the upstream source schema.
    return root_proc.namespaces[namespace] + ref_class


def _parse_ref(ref_value: str) -> tuple[str, str, str]:
    """Parse a ``$ref`` into path, fragment, and class name.

    :param ref_value: JSON Schema ``$ref`` value.
    :return: Ref path, fragment without ``#``, and inferred class name.
    :raises ValueError: If the ref contains multiple fragment operators or an
        unsupported fragment shape.
    """
    parts = ref_value.split("#")
    if len(parts) == 2:  # noqa: PLR2004
        ref_path, fragment = parts
    elif len(parts) == 1:
        ref_path = parts[0]
        fragment = ""
    else:
        msg = "Expected only one fragment operator."
        raise ValueError(msg)

    if not fragment:
        ref_class = ref_path.split("/")[-1].split(".")[0]
        return ref_path, fragment, ref_class

    match = REF_FRAGMENT_RE.match(fragment)
    if match is None:
        msg = f"Unsupported reference fragment: {fragment}"
        raise ValueError(msg)

    return ref_path, fragment, match.group(2)


def _resolve_ref_processor(
    ref_path: str, ref_class: str, root_proc: YamlSchemaProcessor
) -> tuple[YamlSchemaProcessor | None, str]:
    """Resolve the processor that owns a ``$ref`` target.

    :param ref_path: Reference path without the fragment.
    :param ref_class: Class name inferred from the reference.
    :param root_proc: Root schema processor whose imports are searched.
    :return: Owning processor and resolved class name, or ``None`` for unmanaged refs.
    """
    if ref_path == "":
        return root_proc, ref_class

    return _find_import_processor_for_ref(ref_path, ref_class, root_proc)


def _is_protected_ref_for_current_class(
    proc: YamlSchemaProcessor, ref_class: str, dest_path: Path
) -> bool:
    """Check whether a protected ref should stay as a local fragment.

    :param proc: Processor that owns the referenced class.
    :param ref_class: Referenced class name.
    :param dest_path: Destination path for the split schema artifact.
    :return: ``True`` when the protected class belongs inside the current artifact.
    """
    if not proc.class_is_protected(ref_class):
        return False

    containing_class = proc.raw_defs[ref_class]["protectedClassOf"]
    return containing_class == dest_path.name


def _rewrite_ref_for_split_output(
    ref_value: str, dest_path: Path, root_proc: YamlSchemaProcessor, mode: str
) -> str | None:
    """Rewrite one ``$ref`` value for split output.

    :param ref_value: Original ``$ref`` value.
    :param dest_path: Destination path for the split schema artifact.
    :param root_proc: Root schema processor for resolving refs.
    :param mode: Output mode of ``json`` or ``yaml``.
    :return: Rewritten ``$ref`` value, or ``None`` when an unmanaged external ref
        should pass through unchanged.
    :raises ValueError: If the ref has an unsupported fragment shape.
    """
    ref_path, fragment, ref_class = _parse_ref(ref_value)
    proc, ref_class = _resolve_ref_processor(ref_path, ref_class, root_proc)
    if proc is None:
        return None

    if ref_path == "" and _is_protected_ref_for_current_class(
        proc, ref_class, dest_path
    ):
        return f"#{fragment}"

    return proc.get_class_abs_path(ref_class, mode)


def _rewrite_ref_mapping_for_split_output(
    obj: dict, dest_path: Path, root_proc: YamlSchemaProcessor, mode: str
) -> dict:
    """Rewrite refs inside one schema mapping for split output.

    :param obj: Schema mapping. ``$ref`` and ``$refCurie`` entries are rewritten
        on this object.
    :param dest_path: Destination path for the split schema artifact.
    :param root_proc: Root schema processor for resolving local and imported classes.
    :param mode: Output mode of ``json`` or ``yaml``.
    :return: ``obj`` after refs are rewritten.
    :raises ValueError: If a ``$ref`` contains multiple fragment operators or
        an unsupported fragment shape.
    """
    for key, value in list(obj.items()):
        if key == "$refCurie":
            # Most CURIE refs are converted during source processing. This guard
            # keeps split JSON output concrete if inherited data still carries one.
            obj["$ref"] = _resolve_ref_curie(value, root_proc, mode)
            del obj[key]
        elif key == "$ref":
            rewritten_ref = _rewrite_ref_for_split_output(
                value, dest_path, root_proc, mode
            )
            if rewritten_ref is None:
                # External refs that are not class exports stay unchanged.
                return obj

            obj[key] = rewritten_ref
        else:
            obj[key] = _rewrite_refs_for_split_output(value, dest_path, root_proc, mode)

    return obj


def _rewrite_refs_for_split_output(
    obj: JsonValue, dest_path: Path, root_proc: YamlSchemaProcessor, mode: str
) -> JsonValue:
    """Rewrite local and imported class references for split schema output.

    Example:
        A property containing ``{"$ref": "model.json#/$defs/CategoricalVariant"}``
        is rewritten to the imported class output path, such as
        ``{"$ref": "/ga4gh/schema/catvrs/1.0.0/model/json/CategoricalVariant"}``.
        A scalar value such as ``"draft"`` is returned unchanged.

    :param obj: Schema value to process. When ``obj`` is a ``dict``, its ``$ref``
        and ``$refCurie`` entries are rewritten on that same object.
    :param dest_path: Destination path for the split schema artifact.
    :param root_proc: Root schema processor for resolving local and imported classes.
    :param mode: Output mode of ``json`` or ``yaml``.
    :return: ``obj`` after rewriting when it is a ``dict`` or scalar; a new list
        when ``obj`` is a ``list``.
    :raises ValueError: If a ``$ref`` contains multiple fragment operators or
        an unsupported fragment shape.

    """
    if isinstance(obj, list):
        return [
            _rewrite_refs_for_split_output(item, dest_path, root_proc, mode)
            for item in obj
        ]
    if isinstance(obj, dict):
        return _rewrite_ref_mapping_for_split_output(obj, dest_path, root_proc, mode)

    return obj


def _get_output_dir(root_proc: YamlSchemaProcessor, mode: str) -> Path:
    """Get the output directory for split schema artifacts.

    :param root_proc: Root schema processor to split.
    :param mode: Output mode, either ``json`` or ``yaml``.
    :return: Output directory path.
    :raises ValueError: If ``mode`` is not ``json`` or ``yaml``.
    """
    if mode == "json":
        return root_proc.json_fp
    if mode == "yaml":
        return root_proc.yaml_fp

    msg = "mode must be json or yaml"
    raise ValueError(msg)


def _get_protected_defs_for_class(
    root_proc: YamlSchemaProcessor, schema_class: str
) -> dict[str, dict]:
    """Get protected definitions that should be embedded in a split artifact.

    :param root_proc: Root schema processor to split.
    :param schema_class: Public class being written.
    :return: Protected definitions owned directly by ``schema_class``.
    """
    protected_defs: dict[str, dict] = {}
    for protected_class in sorted(
        root_proc.protected_classes_by_container.get(schema_class, [])
    ):
        if root_proc.raw_defs[protected_class]["protectedClassOf"] == schema_class:
            protected_defs[protected_class] = copy.deepcopy(
                root_proc.defs[protected_class]
            )

    return protected_defs


def _build_split_schema_doc(
    root_proc: YamlSchemaProcessor, schema_class: str, target_path: Path, mode: str
) -> dict:
    """Build the output document for one split schema artifact.

    :param root_proc: Root schema processor to split. This processor is read only;
        copied class definitions are rewritten instead.
    :param schema_class: Public class being written.
    :param target_path: Output artifact path.
    :param mode: Output mode, either ``json`` or ``yaml``.
    :return: Split schema document.
    """
    schema_def_key = root_proc.schema_def_keyword
    class_def = copy.deepcopy(root_proc.for_js[schema_def_key][schema_class])
    class_def = _rewrite_refs_for_split_output(class_def, target_path, root_proc, mode)

    out_doc = copy.deepcopy(root_proc.for_js)
    protected_defs = _get_protected_defs_for_class(root_proc, schema_class)
    if protected_defs:
        out_doc[schema_def_key] = _rewrite_refs_for_split_output(
            protected_defs, target_path, root_proc, mode
        )
    else:
        out_doc.pop(schema_def_key, None)

    out_doc.update(class_def)
    out_doc["title"] = schema_class
    out_doc["$id"] = root_proc.get_class_uri(schema_class, mode)
    return out_doc


def _write_split_doc(out_doc: dict, target_path: Path) -> None:
    """Write one split schema document.

    :param out_doc: Schema document to write.
    :param target_path: Output artifact path.
    """
    with target_path.open("w", encoding="utf-8") as f:
        json.dump(out_doc, f, indent=3, sort_keys=False)
        f.write("\n")


def split_defs_to_js(root_proc: YamlSchemaProcessor, mode: str = "json") -> None:
    """Split schema definitions into per-class JSON or YAML artifacts.

    :param root_proc: Root schema processor to split.
    :param mode: Output mode, either ``json`` or ``yaml``.
    :raises ValueError: If ``mode`` is not ``json`` or ``yaml``.
    """
    output_dir = _get_output_dir(root_proc, mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    schema_def_key = root_proc.schema_def_keyword

    for schema_class in root_proc.for_js[schema_def_key]:
        if root_proc.class_is_protected(schema_class):
            continue

        target_path = output_dir / schema_class
        out_doc = _build_split_schema_doc(root_proc, schema_class, target_path, mode)
        _write_split_doc(out_doc, target_path)


def _parse_args() -> argparse.Namespace:
    """Parse split JSON Schema CLI arguments.

    :return: Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("infile")
    return parser.parse_args()


def cli() -> None:
    """Run the split JSON Schema CLI."""
    args = _parse_args()
    p = YamlSchemaProcessor(Path(args.infile))
    split_defs_to_js(p)


if __name__ == "__main__":
    cli()
