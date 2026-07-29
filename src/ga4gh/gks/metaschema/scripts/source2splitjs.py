#!/usr/bin/env python3
"""Write one split JSON Schema artifact per processed class.

Split output rewrites local and imported class refs to the concrete paths
generated from each processor's configured namespace.
"""

import argparse
import copy
import json
import os
import re
from pathlib import Path

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

parser = argparse.ArgumentParser()
parser.add_argument("infile")

JsonValue = str | int | float | bool | None | dict | list


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
    for _, other in root_proc.imports.items():
        if ref_class in other.defs:
            return other, ref_class

    # Fragmentless refs name the generated artifact, e.g. model.json. Match that
    # artifact stem to an import and use the import's single exported class.
    ref_stem = Path(ref).stem
    for _, other in root_proc.imports.items():
        if ref_stem in _get_import_artifact_stems(other):
            return other, _get_primary_exported_class(other)

    return None, ref_class


def _redirect_refs(obj: JsonValue, dest_path: Path, root_proc: YamlSchemaProcessor, mode: str) -> JsonValue:
    """Redirect local and imported class references for split schema output.

    Example:
        A property containing ``{"$ref": "model.json#/$defs/CategoricalVariant"}``
        is rewritten to the imported class output path, such as
        ``{"$ref": "/ga4gh/schema/catvrs/1.0.0/model/json/CategoricalVariant"}``.
        A scalar value such as ``"draft"`` is returned unchanged.

    :param obj: Schema value to process.
    :param dest_path: Destination path for the split schema artifact.
    :param root_proc: Root schema processor for resolving local and imported classes.
    :param mode: Output mode of ``json`` or ``yaml``.
    :return: Schema value with rewritten class references.
    """
    frag_re = re.compile(r"(/\$defs|definitions)/(\w+)")
    if isinstance(obj, list):
        return [_redirect_refs(x, dest_path, root_proc, mode) for x in obj]
    elif isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "$refCurie":
                # Most CURIE refs are converted during source processing. This
                # guard keeps split JSON output concrete if a merged/inherited
                # property still carries a source-level refCurie.
                namespace, ref_class = v.split(":", 1)
                if namespace in root_proc.imports:
                    proc = root_proc.imports[namespace]
                    obj["$ref"] = proc.get_class_abs_path(ref_class, mode)
                else:
                    # Some nested/merged refs use aliases that are available
                    # through rendered namespaces even when no processor import
                    # is attached for the current source.
                    obj["$ref"] = root_proc.namespaces[namespace] + ref_class
                del obj[k]
            elif k == "$ref":
                parts = v.split("#")

                if len(parts) == 2:
                    ref, fragment = parts
                elif len(parts) == 1:
                    ref = parts[0]
                    fragment = ""
                else:
                    raise ValueError("Expected only one fragment operator.")

                if fragment:
                    m = frag_re.match(fragment)
                    if m is None:
                        msg = f"Unsupported reference fragment: {fragment}"
                        raise ValueError(msg)
                    ref_class = m.group(2)
                else:
                    ref_class = ref.split("/")[-1].split(".")[0]

                # Pick the processor that owns the referenced class so the
                # output path is built from that product's configured namespace.
                if ref == "":
                    proc = root_proc
                else:
                    proc, ref_class = _find_import_processor_for_ref(ref, ref_class, root_proc)

                    if proc is None:
                        # External references that are not class exports should pass through.
                        return obj

                # if reference is protected for the class being processed, return only fragment
                if ref == "" and proc.class_is_protected(ref_class):
                    containing_class = proc.raw_defs[ref_class]["protectedClassOf"]
                    if containing_class == dest_path.name:
                        obj[k] = f"#{fragment}"
                        return obj
                obj[k] = proc.get_class_abs_path(ref_class, mode)
            else:
                obj[k] = _redirect_refs(v, dest_path, root_proc, mode)
        return obj
    else:
        return obj


def split_defs_to_js(root_proc: YamlSchemaProcessor, mode: str = "json") -> None:
    """Splits the classes defined in the schema into json files.

    :param root_proc: root YamlSchemaProcessor
    :param mode: str, defaults to "json"
    """
    if mode == "json":
        fp = root_proc.json_fp
    elif mode == "yaml":
        fp = root_proc.yaml_fp
    else:
        raise ValueError("mode must be json or yaml")
    os.makedirs(fp, exist_ok=True)
    kw = root_proc.schema_def_keyword
    for cls in root_proc.for_js[kw].keys():
        if root_proc.class_is_protected(cls):
            continue
        class_def = copy.deepcopy(root_proc.for_js[kw][cls])
        target_path = fp / f"{cls}"
        out_doc = copy.deepcopy(root_proc.for_js)
        if cls in root_proc.has_protected_members:
            def_dict = {}
            keep = False
            for protected_cls in sorted(root_proc.has_protected_members[cls]):
                if root_proc.raw_defs[protected_cls]["protectedClassOf"] == cls:
                    def_dict[protected_cls] = copy.deepcopy(root_proc.defs[protected_cls])
                    keep = True
            if keep:
                out_doc[kw] = _redirect_refs(def_dict, target_path, root_proc, mode)
            else:
                out_doc.pop(kw, None)
        else:
            out_doc.pop(kw, None)
        class_def = _redirect_refs(class_def, target_path, root_proc, mode)
        out_doc.update(class_def)
        out_doc["title"] = cls
        out_doc["$id"] = root_proc.get_class_uri(cls, mode)
        with target_path.open("w", encoding="utf-8") as f:
            json.dump(out_doc, f, indent=3, sort_keys=False)
            f.write("\n")


def cli() -> None:
    """Run the split JSON Schema CLI."""

    args = parser.parse_args()
    p = YamlSchemaProcessor(Path(args.infile))
    split_defs_to_js(p)


if __name__ == "__main__":
    cli()
