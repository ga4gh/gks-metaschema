"""Import-loading and merge helpers for source schema processing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ga4gh.gks.metaschema.tools.source_proc.paths import normalize_local_ref_paths

if TYPE_CHECKING:
    from ga4gh.gks.metaschema.tools.source_proc.processor import YamlSchemaProcessor


def import_dependencies(processor: YamlSchemaProcessor) -> None:
    """Load configured imports as child schema processors.

    :param processor: Owning schema processor.
    """
    from ga4gh.gks.metaschema.tools.source_proc.processor import YamlSchemaProcessor

    for alias, imported_path in processor.raw_schema.get("imports", {}).items():
        processor.imports[alias] = YamlSchemaProcessor(
            imported_path, root_fp=processor.root_schema_fp or processor.schema_fp
        )


def merge_imported_definitions(processor: YamlSchemaProcessor) -> None:
    """Merge imported schema definitions into the current processor.

    Example:
        If the root schema imports ``vrs`` and references ``vrs:Allele``, the
        merged schema copies imported class definitions into the root schema,
        rewrites inherited CURIE references to local class names, and rebuilds
        processed state from the merged definitions.

    :param processor: Owning schema processor.
    :raises ValueError: If imported schemas define duplicate class names or use
        conflicting import aliases.

    """
    processor.import_locations = {}
    processor.import_processors = {}
    processor.import_process_order = []
    _register_import_for_merge(processor, processor)
    _validate_unique_merge_classes(processor)
    _merge_import_definitions(processor)
    _normalize_merged_definition_refs(processor)
    processor.imports = {}
    processor.raw_schema["title"] = processor.raw_schema["title"] + "-Merged-Imports"
    processor.raw_defs = processor.raw_schema.get(processor.schema_def_keyword, None)
    processor._rebuild_processed_state()


def _register_import_for_merge(processor: YamlSchemaProcessor, current: YamlSchemaProcessor) -> None:
    """Register imports in dependency order for merging.

    :param processor: Root processor receiving merged imports.
    :param current: Processor whose imports should be registered.
    :raises ValueError: If the same import alias resolves to different files.
    """
    for alias, imported_processor in current.imports.items():
        _register_import_for_merge(processor, imported_processor)
        if alias in processor.import_locations:
            if processor.import_locations[alias] != imported_processor.schema_fp:
                msg = (
                    f"Import {alias} resolves to multiple locations: "
                    f"{processor.import_locations[alias]} and "
                    f"{imported_processor.schema_fp}"
                )
                raise ValueError(msg)
            continue

        processor.import_locations[alias] = imported_processor.schema_fp
        processor.import_processors[alias] = imported_processor
        processor.import_process_order.append(alias)


def _validate_unique_merge_classes(processor: YamlSchemaProcessor) -> None:
    """Validate that merged schemas do not define duplicate classes.

    :param processor: Root processor receiving merged imports.
    :raises ValueError: If any imported class conflicts with another class name.
    """
    defined_classes = set(processor.processed_classes)
    for alias in processor.import_process_order:
        imported_processor = processor.import_processors[alias]
        duplicate_classes = defined_classes & imported_processor.processed_classes
        if duplicate_classes:
            msg = (
                f"Imported schema {imported_processor.schema_fp} defines duplicate "
                f"class(es): {', '.join(sorted(duplicate_classes))}"
            )
            raise ValueError(msg)
        defined_classes.update(imported_processor.processed_classes)


def _merge_import_definitions(processor: YamlSchemaProcessor) -> None:
    """Copy imported definitions and localize import namespaces.

    :param processor: Root processor receiving merged imports.
    """
    for alias in processor.import_process_order:
        processor.namespaces[alias] = f"#/{processor.schema_def_keyword}/"
        imported_processor = processor.import_processors[alias]
        processor.raw_defs.update(imported_processor.raw_defs)


def _normalize_merged_definition_refs(processor: YamlSchemaProcessor) -> None:
    """Normalize inherited classes and refs after import definitions are merged.

    :param processor: Root processor receiving merged imports.
    """
    for schema_class in set(processor.raw_defs):
        inherits_value = processor.raw_defs[schema_class].get("inherits", "")
        if ":" in inherits_value:
            processor.raw_defs[schema_class]["inherits"] = inherits_value.split(":")[1]

        processor.raw_defs[schema_class] = normalize_local_ref_paths(processor, processor.raw_defs[schema_class])
