"""Metaschema config helpers for source schema processing."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from ga4gh.gks.metaschema.tools.config import (
    ALLOWED_CONFIG_KEYS,
    METASCHEMA_FN,
    find_metaschema_config,
    find_stale_schema_url_versions,
    load_imported_versions,
    load_metaschema_config,
    render_namespaces,
)

if TYPE_CHECKING:
    from ga4gh.gks.metaschema.tools.source_proc.processor import YamlSchemaProcessor


def apply_metaschema_config(processor: YamlSchemaProcessor) -> None:
    """Apply owning ``metaschema.yaml`` settings to a source schema.

    Example:
        A source schema that uses ``$refCurie: vrs:Allele`` receives the
        configured ``vrs`` import and rendered ``vrs`` namespace from the owning
        ``metaschema.yaml``. Source-local ``imports``, ``namespaces``, and
        ``versions`` are removed because the metaschema config is authoritative.

    :param processor: Owning schema processor.

    """
    config_fp = get_metaschema_config_fp(processor)
    if config_fp is None:
        return

    metaschema_config = load_metaschema_config(config_fp)
    config_versions = load_imported_versions(config_fp, metaschema_config.imports) | metaschema_config.versions
    if "$id" in processor.raw_schema:
        validate_schema_id_versions(processor, config_versions)

    _remove_source_local_config(processor, config_fp)
    used_aliases = _find_referenced_config_aliases(processor, metaschema_config.imports)
    imports = _resolve_used_config_imports(processor, config_fp, metaschema_config.imports, used_aliases)
    if imports:
        processor.raw_schema["imports"] = imports

    namespaces = render_namespaces(metaschema_config.namespaces, config_versions)
    if namespaces:
        processor.raw_schema["namespaces"] = {key: value for key, value in namespaces.items() if key in used_aliases}


def validate_schema_id_versions(processor: YamlSchemaProcessor, versions: dict[str, str]) -> None:
    """Validate that the source ``$id`` uses configured concrete versions.

    :param processor: Owning schema processor.
    :param versions: Version strings keyed by spec name.
    :raises ValueError: If the source ``$id`` has a stale or templated version.
    """
    stale_versions = find_stale_schema_url_versions(processor.raw_schema["$id"], versions)
    if not stale_versions:
        return

    products = ", ".join(item.spec for item in stale_versions)
    actual_versions = ", ".join(item.actual_version for item in stale_versions)
    expected_versions = ", ".join(item.expected_version for item in stale_versions)
    msg = f"{processor.schema_fp}: {products} $id version is {actual_versions}; expected {expected_versions}"
    raise ValueError(msg)


def get_metaschema_config_fp(processor: YamlSchemaProcessor) -> Path | None:
    """Return the owning ``metaschema.yaml`` path, if present.

    :param processor: Owning schema processor.
    :return: Path to the owning metaschema config, if one exists.
    """
    return find_metaschema_config(processor.schema_fp)


def _remove_source_local_config(processor: YamlSchemaProcessor, config_fp: Path) -> None:
    """Remove config keys that must be defined only in ``metaschema.yaml``.

    :param processor: Owning schema processor.
    :param config_fp: Owning metaschema config path.
    """
    disallowed_keys = ALLOWED_CONFIG_KEYS & set(processor.raw_schema)
    if not disallowed_keys:
        return

    keys = ", ".join(sorted(disallowed_keys))
    msg = (
        f"{processor.schema_fp} is managed by {config_fp}, so ignoring source-local "
        f"{keys}. Define these values only in {METASCHEMA_FN}."
    )
    warnings.warn(msg, stacklevel=2)

    for key in disallowed_keys:
        processor.raw_schema.pop(key, None)


def _resolve_used_config_imports(
    processor: YamlSchemaProcessor,
    config_fp: Path,
    config_imports: dict[str, str],
    used_aliases: set[str],
) -> dict[str, str]:
    """Return configured imports used by the current source schema.

    :param processor: Owning schema processor.
    :param config_fp: Owning metaschema config path.
    :param config_imports: Import aliases and source paths from config.
    :param used_aliases: Namespace aliases referenced by this source.
    :return: Import aliases and absolute source paths for the schema.
    """
    resolved_imports: dict[str, str] = {}
    for alias, import_value in config_imports.items():
        if alias not in used_aliases:
            continue

        import_fp = Path(import_value)
        if not import_fp.is_absolute():
            import_fp = config_fp.parent / import_fp

        if import_fp.resolve() == processor.schema_fp.resolve():
            continue

        resolved_imports[alias] = str(import_fp)
    return resolved_imports


def _find_referenced_config_aliases(processor: YamlSchemaProcessor, config_imports: dict[str, str]) -> set[str]:
    """Return namespace aliases referenced by the source schema.

    :param processor: Owning schema processor.
    :param config_imports: Import aliases and source paths from config.
    :return: Namespace aliases used by refs, inheritance, or external ``$ref`` paths.
    """
    used_aliases: set[str] = set()
    import_stems = _get_config_import_stems(config_imports)

    def collect(node: object) -> None:
        """Collect referenced aliases from one schema node.

        :param node: Schema node to inspect.
        """
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"$refCurie", "inherits"} and isinstance(value, str) and ":" in value:
                    used_aliases.add(value.split(":", 1)[0])
                elif key == "$ref" and isinstance(value, str):
                    used_aliases.update(_get_ref_import_aliases(value, import_stems))
                collect(value)
            return

        if isinstance(node, list):
            for item in node:
                collect(item)

    collect(processor.raw_schema)
    return used_aliases


def _get_config_import_stems(config_imports: dict[str, str]) -> dict[str, set[str]]:
    """Return generated artifact stems for configured source imports.

    :param config_imports: Mapping of import aliases to source schema paths.
    :return: Candidate generated artifact stems keyed by alias.
    """
    import_stems: dict[str, set[str]] = {}
    for alias, import_value in config_imports.items():
        source_stem = Path(import_value).stem
        artifact_stem = source_stem.removesuffix("-source")
        import_stems[alias] = {alias, source_stem, artifact_stem}
    return import_stems


def _get_ref_import_aliases(ref: str, import_stems: dict[str, set[str]]) -> set[str]:
    """Return configured import aliases referenced by an external ``$ref``.

    :param ref: JSON Schema ``$ref`` value.
    :param import_stems: Candidate generated artifact stems keyed by alias.
    :return: Import aliases referenced by the ``$ref`` path.
    """
    ref_path = ref.split("#", 1)[0]
    if not ref_path:
        return set()

    ref_stem = Path(ref_path).stem
    return {alias for alias, stems in import_stems.items() if ref_stem in stems}
