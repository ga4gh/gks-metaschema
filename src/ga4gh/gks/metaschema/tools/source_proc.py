#!/usr/bin/env python3
"""Process GKS source YAML into resolved schema artifacts.

The processor applies product-level metaschema config, resolves imports and
CURIE references, and prepares JSON/YAML schema output structures.
"""

import copy
import json
import re
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

import yaml

from ga4gh.gks.metaschema.tools.config import (
    ALLOWED_CONFIG_KEYS,
    METASCHEMA_FN,
    find_metaschema_config,
    find_stale_schema_url_versions,
    load_imported_versions,
    load_metaschema_config,
    render_namespaces,
)

SCHEMA_DEF_KEYWORD_BY_VERSION = {
    "https://json-schema.org/draft-07/schema": "definitions",
    "https://json-schema.org/draft/2020-12/schema": "$defs",
}


ref_re = re.compile(r":ref:`(.*?)(\s?<.*>)?`")
link_re = re.compile(r"`(.*?)\s?\<(.*)\>`_")
curie_re = re.compile(r"(\S+):(\S+)")
defs_re = re.compile(r"#/(\$defs|definitions)/.*")

maturity_levels = {"deprecated": 0, "draft": 1, "trial use": 2, "normative": 3}


@dataclass
class ClassProcessingState:
    """Mutable state collected while processing one schema class.

    :param inherited_properties: Inherited properties not yet merged into the class.
    :param inherited_required: Inherited required fields not yet merged into the class.
    :param class_properties: Local class properties being processed.
    :param class_required: Local required fields being processed.
    """

    inherited_properties: dict[str, Any]
    inherited_required: set[str]
    class_properties: dict[str, Any]
    class_required: set[str]


class YamlSchemaProcessor:
    """Process a GKS source YAML file into resolved schema representations.

    The processor loads one source schema, applies any owning ``metaschema.yaml``
    configuration, resolves imports and CURIE refs, validates GKS schema
    conventions, and prepares structures used by YAML, JSON Schema, and RST
    generation.

    Processing lifecycle:
        load raw YAML, apply metaschema config, import dependencies, rebuild
        processed state, then clean the JSON Schema output copy.
    """

    def __init__(self, schema_fp: Path, root_fp: Path | None = None) -> None:
        """Initialize a YAML schema processor.

        :param schema_fp: Path to the source YAML schema.
        :param root_fp: Root source YAML path when processing an imported schema.
        """
        self.schema_fp = Path(schema_fp).resolve()
        self.imported = root_fp is not None
        self.root_schema_fp = Path(root_fp).resolve() if root_fp is not None else None
        self.raw_schema = self.load_schema(self.schema_fp)
        self.apply_metaschema_config()
        self.id = self.raw_schema["$id"]
        self.yaml_key = self.raw_schema.get("yaml-target", "yaml")
        self.json_key = self.raw_schema.get("json-target", "json")
        self.defs_key = self.raw_schema.get("def-target", "def")
        self.yaml_fp = self.schema_fp.parent / self.yaml_key
        self.json_fp = self.schema_fp.parent / self.json_key
        self.def_fp = self.schema_fp.parent / self.defs_key
        self.namespaces = self.raw_schema.get("namespaces", [])
        self.schema_def_keyword = SCHEMA_DEF_KEYWORD_BY_VERSION[self.raw_schema["$schema"]]
        self.raw_defs = self.raw_schema.get(self.schema_def_keyword, None)
        self.imports = {}
        self.import_dependencies()
        self.strict = self.raw_schema.get("strict", False)
        self.enforce_ordered = self.raw_schema.get("enforce_ordered", self.strict)
        self._rebuild_processed_state()

    def _rebuild_processed_state(self) -> None:
        """Rebuild processor-derived state from ``raw_schema``.

        Replaces ``child_ref_urls_by_parent_ref``, ``child_classes_by_parent``,
        ``protected_classes_by_container``, ``processed_schema``, ``defs``,
        ``processed_classes``, and ``for_js`` on this processor.
        """
        self.child_ref_urls_by_parent_ref = {}
        self.child_classes_by_parent = {}
        self.build_class_relationship_maps()
        self.protected_classes_by_container = defaultdict(set)
        self.processed_schema = copy.deepcopy(self.raw_schema)
        self.defs = self.processed_schema.get(self.schema_def_keyword, None)
        self.processed_classes = set()
        self.process_schema()
        self.check_processed_schema()
        self.for_js = copy.deepcopy(self.processed_schema)
        self.clean_for_js()

    def build_class_relationship_maps(self) -> None:
        """Build class inheritance and container-child lookup maps.

        Updates ``self.child_ref_urls_by_parent_ref`` and
        ``self.child_classes_by_parent``.
        """
        for schema_class, class_def in self.raw_defs.items():
            class_ref = f"#/{self.schema_def_keyword}/{schema_class}"
            if self.class_is_container(schema_class):
                self._register_container_children(schema_class, class_ref, class_def)

            if "inherits" in class_def:
                self._register_inherited_child(schema_class, class_ref, class_def["inherits"])

    def _register_container_children(self, schema_class: str, class_ref: str, class_def: dict[str, Any]) -> None:
        """Register concrete children listed by an abstract container class.

        Updates ``self.child_ref_urls_by_parent_ref`` and
        ``self.child_classes_by_parent``.

        :param schema_class: Container class name.
        :param class_ref: Local reference URL for the container class.
        :param class_def: Raw container class definition.
        """
        child_urls = self.child_ref_urls_by_parent_ref.get(class_ref, set())
        child_classes = self.child_classes_by_parent.get(schema_class, set())

        for record in self._get_container_child_records(class_def):
            if not isinstance(record, dict):
                continue

            child_url = self._get_child_ref(record)
            child_urls.add(child_url)
            child_classes.add(child_url.split("/")[-1])

        self.child_ref_urls_by_parent_ref[class_ref] = child_urls
        self.child_classes_by_parent[schema_class] = child_classes

    @staticmethod
    def _get_container_child_records(class_def: dict[str, Any]) -> list[dict[str, str]]:
        """Get child records from a container class definition.

        :param class_def: Raw container class definition.
        :return: Container child refs.
        """
        for key in ("oneOf", "anyOf", "allOf"):
            if key in class_def:
                return class_def[key]

        return [{"$ref": class_def["$ref"]}]

    def _get_child_ref(self, record: dict[str, str]) -> str:
        """Get a concrete child reference from a container record.

        :param record: Container child record.
        :return: Concrete child reference.
        """
        if "$refCurie" in record:
            return self.resolve_curie(record["$refCurie"])

        return record["$ref"]

    def _register_inherited_child(self, schema_class: str, class_ref: str, target: str) -> None:
        """Register a class as a child of its local inherited parent.

        Updates ``self.child_ref_urls_by_parent_ref`` and
        ``self.child_classes_by_parent`` when ``target`` is local.

        :param schema_class: Child class name.
        :param class_ref: Local reference URL for the child class.
        :param target: Inherited class name or CURIE.
        """
        if ":" in target:
            return

        target_url = f"#/{self.schema_def_keyword}/{target}"
        child_urls = self.child_ref_urls_by_parent_ref.get(target_url, set())
        child_classes = self.child_classes_by_parent.get(target, set())
        child_urls.add(class_ref)
        child_classes.add(schema_class)
        self.child_ref_urls_by_parent_ref[target_url] = child_urls
        self.child_classes_by_parent[target] = child_classes

    def get_all_descendants(self, cls: str) -> set[str]:
        """Get all classes that descend from a class.

        :param cls: Class name to inspect.
        :return: Descendant class names.
        """
        out: set[str] = set()
        for descendant in self.child_classes_by_parent.get(cls, []):
            out.add(descendant)
            out.update(self.get_all_descendants(descendant))
        return out

    def merge_imported_definitions(self) -> None:
        """Merge imported schema definitions into the current processor.

        Imported classes are copied into the root schema, import CURIEs are rewritten
        to local definition refs, and duplicate class names are rejected.

        Example:
            If the root schema imports ``vrs`` and references ``vrs:Allele``,
            ``merge_imported_definitions()`` adds the imported VRS definitions and rewrites
            inherited references to local ``#/$defs/...`` paths.

        :raises ValueError: If merged imports define duplicate classes or contain
            non-local ``$ref`` values that cannot be merged safely.
        """
        self._initialize_merge_state()
        self._validate_unique_merge_classes()
        self._merge_import_definitions()
        self._normalize_merged_definition_refs()
        self._finalize_import_merge()

    def _initialize_merge_state(self) -> None:
        """Reset and populate import merge state on the processor."""
        self.import_locations = {}
        self.import_processors = {}
        self.import_process_order = []
        self._register_import_for_merge(self)

    def _validate_unique_merge_classes(self) -> None:
        """Validate that merged schemas do not define the same class names.

        :raises ValueError: If any imported class name conflicts with another
            imported or local class.
        """
        defined_classes = self.processed_classes
        for key in self.import_process_order:
            other = self.import_processors[key]
            duplicate_classes = defined_classes & other.processed_classes

            if duplicate_classes:
                msg = (
                    f"Imported schema {other.schema_fp} defines duplicate class(es): "
                    f"{', '.join(sorted(duplicate_classes))}"
                )
                raise ValueError(msg)

            defined_classes.update(other.processed_classes)

    def _merge_import_definitions(self) -> None:
        """Copy imported definitions and localize import namespaces.

        Updates ``self.raw_defs`` and ``self.namespaces``.
        """
        for key in self.import_process_order:
            self.namespaces[key] = f"#/{self.schema_def_keyword}/"
            other = self.import_processors[key]
            other_ns = other.raw_schema.get("namespaces", [])
            if other_ns:
                for ns in other_ns:
                    if ns not in self.import_process_order:
                        # Imported schemas may point at external schemas that
                        # are not part of this merge. Preserve those namespaces.
                        self.namespaces[key] = other.namespaces[key]
            self.raw_defs.update(other.raw_defs)

    def _normalize_merged_definition_refs(self) -> None:
        """Normalize inherited classes and refs after import definitions are merged.

        Updates merged class definitions in ``self.raw_defs``.

        :raises ValueError: If a merged ``$ref`` points outside local definitions.
        """
        defined_classes = set(self.raw_defs)
        for schema_class in defined_classes:
            inherits_value = self.raw_defs[schema_class].get("inherits", "")
            if curie_re.match(inherits_value):
                self.raw_defs[schema_class]["inherits"] = inherits_value.split(":")[1]

            self.raw_defs[schema_class] = self._normalize_local_ref_paths(self.raw_defs[schema_class])

    def _finalize_import_merge(self) -> None:
        """Clear import metadata and rebuild processor state after a merge."""
        self.imports = {}
        self.raw_schema["title"] = self.raw_schema["title"] + "-Merged-Imports"
        self.raw_defs = self.raw_schema.get(self.schema_def_keyword, None)
        self._rebuild_processed_state()

    def _normalize_local_ref_paths(self, obj: object) -> object:
        """Normalize local definition refs in a schema object.

        Example:
            ``{"$ref": "#/definitions/Thing"}`` becomes
            ``{"$ref": "#/$defs/Thing"}`` when the active schema dialect uses
            ``$defs``.

        :param obj: Schema node to inspect recursively. If ``obj`` is a ``dict``,
            local ``$ref`` values and nested list fields are rewritten on that same
            mapping.
        :return: ``obj`` after normalization when it is a ``dict`` or scalar; a
            rebuilt list when a list is reached through a containing dict.
        :raises ValueError: If a ``$ref`` is not a local ``$defs`` or
            ``definitions`` reference.
        """
        if isinstance(obj, list):
            return [self._normalize_local_ref_paths(element) for element in obj]

        if not isinstance(obj, dict):
            return obj

        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                obj[key] = self._normalize_local_ref_paths(value)
            elif isinstance(value, str) and key == "$ref":
                obj[key] = self._normalize_local_ref_path(value)

        return obj

    def _normalize_local_ref_path(self, ref: str) -> str:
        """Normalize one local definition ref path.

        :param ref: Local ``$ref`` value.
        :return: Ref path using this schema's definition keyword.
        :raises ValueError: If ``ref`` is not a local ``$defs`` or
            ``definitions`` reference.
        """
        match = defs_re.match(ref)
        if match is None:
            msg = f'Expected local "$ref" definition path, got {ref}.'
            raise ValueError(msg)

        if match.group(1) == self.schema_def_keyword:
            return ref

        return re.sub(re.escape(match.group(1)), self.schema_def_keyword, ref)

    def _register_import_for_merge(self, proc: "YamlSchemaProcessor") -> None:
        """Register imports in the order needed for merging.

        Example:
            If ``root`` imports ``mid`` and ``mid`` imports ``upstream``, this
            records ``upstream`` before ``mid`` so dependencies merge first.

        :param proc: Processor whose imports should be registered.
        :raises ValueError: If the same import alias resolves to different files.
        """
        for name, other in proc.imports.items():
            self._register_import_for_merge(other)
            if name in self.import_locations:
                # check that all imports from imported point to same locations
                if self.import_locations[name] != other.schema_fp:
                    msg = (
                        f"Import {name} resolves to multiple locations: "
                        f"{self.import_locations[name]} and {other.schema_fp}"
                    )
                    raise ValueError(msg)
            else:
                self.import_locations[name] = other.schema_fp
                self.import_processors[name] = other
                self.import_process_order.append(name)
        return

    @staticmethod
    def load_schema(schema_fp: Path) -> dict[str, object]:
        """Load a source YAML schema file.

        :param schema_fp: Path to the source YAML schema.
        :return: Parsed schema mapping.
        """
        with open(schema_fp, encoding="utf-8") as f:
            schema = yaml.load(f, Loader=yaml.SafeLoader)
        return schema

    def apply_metaschema_config(self) -> None:
        """Apply project-level metaschema config to the root source schema.

        Config imports pointing back to the schema currently being loaded are skipped to
        avoid recursive self-imports. When config is applied, source-local ``imports``
        and ``namespaces`` are ignored with a warning so the project config remains
        authoritative.

        Example:
            A source containing ``$refCurie: vrs:Allele`` receives the configured
            ``vrs`` import and rendered ``vrs`` namespace from
            ``schema/<product>/metaschema.yaml``.
        """
        config_fp = self.get_metaschema_config_fp()
        if config_fp is None:
            return

        config = load_metaschema_config(config_fp)
        config_versions = load_imported_versions(config_fp, config.imports) | config.versions
        if "$id" in self.raw_schema:
            self.validate_schema_id_versions(config_versions)

        self._remove_source_local_config(config_fp)

        used_namespaces = self._find_referenced_config_aliases(config.imports)
        imports = self._resolve_used_config_imports(config_fp, config.imports, used_namespaces)
        if imports:
            self.raw_schema["imports"] = imports

        namespaces = render_namespaces(config.namespaces, config_versions)
        if namespaces:
            self.raw_schema["namespaces"] = {key: value for key, value in namespaces.items() if key in used_namespaces}

    def _remove_source_local_config(self, config_fp: Path) -> None:
        """Remove config sections that must be managed by ``metaschema.yaml``.

        Removes managed source-local keys from ``self.raw_schema``.

        :param config_fp: Owning metaschema config path.
        """
        disallowed_keys = ALLOWED_CONFIG_KEYS & set(self.raw_schema)
        if not disallowed_keys:
            return

        keys = ", ".join(sorted(disallowed_keys))
        warnings.warn(
            f"{self.schema_fp} is managed by {config_fp}, so ignoring source-local {keys}. "
            f"Define these values only in {METASCHEMA_FN}.",
            stacklevel=2,
        )

        for key in disallowed_keys:
            self.raw_schema.pop(key, None)

    def _resolve_used_config_imports(
        self, config_fp: Path, config_imports: dict[str, str], used_namespaces: set[str]
    ) -> dict[str, str]:
        """Get configured imports used by the current source schema.

        :param config_fp: Owning metaschema config path.
        :param config_imports: Import aliases and source paths from config.
        :param used_namespaces: Namespace aliases referenced by this source.
        :return: Import aliases and absolute source paths to attach to the schema.
        """
        imports: dict[str, str] = {}

        for key, import_value in config_imports.items():
            if key not in used_namespaces:
                continue

            import_fp = Path(import_value)

            if not import_fp.is_absolute():
                import_fp = config_fp.parent / import_fp

            if import_fp.resolve() == self.schema_fp.resolve():
                continue

            imports[key] = str(import_fp)

        return imports

    def _find_referenced_config_aliases(self, config_imports: dict[str, str] | None = None) -> set[str]:
        """Get namespace aliases referenced by the source schema.

        Example:
            A schema using ``$refCurie: vrs:Allele`` and
            ``$ref: "model.json"`` returns ``{"vrs", "model"}`` when the
            config imports include ``model: model-source.yaml``.

        :param config_imports: Mapping of import aliases to source schema paths.
        :return: Namespace aliases used by refs, inheritance, or external ``$ref`` paths.
        """
        used_namespaces: set[str] = set()
        import_stems = self._get_config_import_stems(config_imports or {})

        def collect(node: object) -> None:
            """Collect namespace aliases from a schema node.

            :param node: Source schema node.
            """
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in {"$refCurie", "inherits"} and isinstance(value, str) and ":" in value:
                        used_namespaces.add(value.split(":", 1)[0])
                    elif key == "$ref" and isinstance(value, str):
                        used_namespaces.update(self._get_ref_import_aliases(value, import_stems))
                    collect(value)
            elif isinstance(node, list):
                for item in node:
                    collect(item)

        collect(self.raw_schema)
        return used_namespaces

    @staticmethod
    def _get_config_import_stems(config_imports: dict[str, str]) -> dict[str, set[str]]:
        """Get generated artifact stems for configured source imports.

        Example:
            ``{"model": "model-source.yaml"}`` returns
            ``{"model": {"model", "model-source"}}``.

        :param config_imports: Mapping of import aliases to source schema paths.
        :return: Candidate generated artifact stems keyed by alias.
        """
        import_stems: dict[str, set[str]] = {}
        for alias, import_value in config_imports.items():
            source_stem = Path(import_value).stem
            artifact_stem = source_stem.removesuffix("-source")
            import_stems[alias] = {alias, source_stem, artifact_stem}
        return import_stems

    @staticmethod
    def _get_ref_import_aliases(ref: str, import_stems: dict[str, set[str]]) -> set[str]:
        """Get configured import aliases referenced by an external ``$ref``.

        Example:
            ``model.json#/$defs/CategoricalVariant`` returns ``{"model"}``
            when ``import_stems["model"]`` contains ``"model"``.

        :param ref: JSON Schema ``$ref`` value.
        :param import_stems: Candidate generated artifact stems keyed by alias.
        :return: Import aliases referenced by the ``$ref`` path.
        """
        ref_path = ref.split("#", 1)[0]
        if not ref_path:
            return set()

        ref_stem = Path(ref_path).stem
        return {alias for alias, stems in import_stems.items() if ref_stem in stems}

    def validate_schema_id_versions(self, versions: dict[str, str]) -> None:
        """Validate that the source ``$id`` uses configured concrete versions.

        Example:
            A source ``$id`` containing ``/vrs/{version}/`` raises when
            ``versions["vrs"] == "2.2.0"``; the source must contain
            ``/vrs/2.2.0/``.

        :param versions: Version strings keyed by spec name.
        :raises ValueError: If the source ``$id`` has a stale or templated version.
        """
        stale_versions = find_stale_schema_url_versions(self.raw_schema["$id"], versions)
        if not stale_versions:
            return

        messages = [
            f"{version.spec} $id version is {version.actual_version}; expected {version.expected_version}"
            for version in stale_versions
        ]
        msg = f"{self.schema_fp}: " + "; ".join(messages)
        raise ValueError(msg)

    def get_metaschema_config_fp(self) -> Path | None:
        """Find the project-level metaschema config file.

        :return: Path to the owning ``metaschema.yaml`` file, or ``None`` if absent.
        """
        return find_metaschema_config(self.schema_fp)

    def import_dependencies(self) -> None:
        """Load configured imports as child schema processors."""
        for dependency in self.raw_schema.get("imports", []):
            fp = Path(self.raw_schema["imports"][dependency])
            if not fp.is_absolute():
                base_path = self.schema_fp.parent
                fp = base_path.joinpath(fp)
            if self.imported:
                root_fp = self.root_schema_fp
            else:
                root_fp = self.schema_fp
            self.imports[dependency] = YamlSchemaProcessor(fp, root_fp=root_fp)

    def process_schema(self) -> None:
        """Process all source schema class definitions."""
        if self.defs is None:
            return

        for schema_class in self.defs:
            self.process_schema_class(schema_class)

    def check_processed_schema(self) -> None:
        """Validate relationships after all classes are processed.

        Example:
            A ``normative`` class that inherits from a ``draft`` parent is rejected
            because a child cannot have greater maturity than its parent.

        :raises ValueError: If inherited classes are missing maturity values or a
            child class has greater maturity than its parent.
        """
        for schema_class in self.processed_classes:
            class_def = self.defs[schema_class]
            if "inherits" in class_def:
                inherited_class_name = class_def["inherits"]
                if ":" in inherited_class_name:
                    namespace, inherited_class_split_name = inherited_class_name.split(":")
                    inherited_class_def = self.imports[namespace].defs[inherited_class_split_name]
                else:
                    inherited_class_def = self.defs[inherited_class_name]

                if "maturity" not in class_def:
                    msg = f"{schema_class} is missing a maturity value."
                    raise ValueError(msg)

                if "maturity" not in inherited_class_def:
                    msg = f"{inherited_class_name} is missing a maturity value."
                    raise ValueError(msg)

                if inherited_class_def["maturity"] < class_def["maturity"]:
                    msg = f"Maturity of {schema_class} is greater than parent class {inherited_class_name}."
                    raise ValueError(msg)
            pass

    def class_is_abstract(self, schema_class: str) -> bool:
        """Check whether a schema class is abstract.

        :param schema_class: Class name to inspect.
        :return: ``True`` when the class has no concrete properties and is not primitive.
        """
        schema_class_def, _ = self.get_class_definition(schema_class, raw=True)
        return "properties" not in schema_class_def and not self.class_is_primitive(schema_class)

    def class_is_container(self, schema_class: str) -> bool:
        """Check whether a schema class is an abstract container.

        :param schema_class: Class name to inspect.
        :return: ``True`` when the class enumerates children with ``oneOf``,
            ``anyOf``, or ``allOf``.
        """
        class_def, _ = self.get_class_definition(schema_class, raw=True)
        return self.class_is_abstract(schema_class) and (
            "oneOf" in class_def or "anyOf" in class_def or "allOf" in class_def
        )

    def class_is_protected(self, schema_class: str) -> bool:
        """Check whether a class is protected under another class.

        :param schema_class: Class name to inspect.
        :return: ``True`` when the class declares ``protectedClassOf``.
        """
        schema_class_def, _ = self.get_class_definition(schema_class, raw=True)
        return "protectedClassOf" in schema_class_def

    def class_is_ga4gh_identifiable(self, schema_class: str) -> bool:
        """Check whether a class declares GA4GH identifier metadata.

        :param schema_class: Class name to inspect.
        :return: ``True`` when the class has a ``ga4gh.prefix`` value.
        """
        schema_class_def, _ = self.get_class_definition(schema_class, raw=True)
        return "ga4gh" in schema_class_def and "prefix" in schema_class_def["ga4gh"]

    def class_is_passthrough(self, schema_class: str) -> bool:
        """Check whether an abstract class only passes through an inherited class.

        :param schema_class: Class name to inspect.
        :return: ``True`` when the class inherits without defining local property maps.
        """
        if not self.class_is_abstract(schema_class):
            return False
        raw_class_definition, _ = self.get_class_definition(schema_class, raw=True)
        if (
            "heritableProperties" not in raw_class_definition
            and "properties" not in raw_class_definition
            and raw_class_definition.get("inherits", False)
        ):
            return True
        return False

    def class_is_primitive(self, schema_class: str) -> bool:
        """Check whether a class represents a primitive JSON Schema value.

        :param schema_class: Class name to inspect.
        :return: ``True`` when the class type is neither ``abstract`` nor ``object``.
        """
        schema_class_def, _ = self.get_class_definition(schema_class, raw=True)
        schema_class_type = schema_class_def.get("type", "abstract")
        if schema_class_type not in ["abstract", "object"]:
            return True
        return False

    def class_is_subclass(self, schema_class: str, parent_class: str) -> bool:
        """Check whether a class descends from another class.

        :param schema_class: Candidate child class name.
        :param parent_class: Candidate parent class name.
        :return: ``True`` when the child is reachable from the parent hierarchy.
        """
        schema_class_fragment = f"#/{self.schema_def_keyword}/{schema_class}"
        parent_class_fragment = f"#/{self.schema_def_keyword}/{parent_class}"
        children = self.get_concrete_class_refs(parent_class_fragment)
        return schema_class_fragment in children

    def js_json_dump(self, stream: TextIO) -> None:
        """Write the processed JSON Schema representation as formatted JSON.

        :param stream: Writable text stream.
        """
        json.dump(self.for_js, stream, indent=3, sort_keys=False)

    def js_yaml_dump(self, stream: TextIO) -> None:
        """Write the processed JSON Schema representation as YAML.

        :param stream: Writable text stream.
        """
        yaml.dump(self.for_js, stream, sort_keys=False)

    def resolve_curie(self, curie: str) -> str:
        """Resolve a configured ``$refCurie`` into a concrete reference URL.

        MSP treats ``$refCurie`` as source-authoring syntax only. Processed and
        generated artifacts should contain concrete ``$ref`` URLs instead.

        Example:
            ``vrs:Allele`` becomes ``/ga4gh/schema/vrs/2.2.0/json/Allele`` when
            ``namespaces["vrs"]`` is configured with that base path.

        :param curie: CURIE value using a configured namespace alias.
        :return: Concrete reference URL.
        """
        namespace, identifier = curie.split(":")
        base_url = self.namespaces[namespace]
        return base_url + identifier

    def resolve_property_tree_refs(self, raw_node: Any, processed_node: Any) -> None:
        """Resolve refs inside a raw/processed property tree pair.

        ``raw_node`` controls which keys were present in the source YAML. Matching
        entries in ``processed_node`` are updated so generated outputs contain
        concrete ``$ref`` values instead of ``$refCurie``.

        :param raw_node: Source schema node.
        :param processed_node: Processed schema node. Matching ``$refCurie`` and
            imported local ``$ref`` entries are rewritten on this object.
        :raises ValueError: If an imported processor is missing its root schema path.
        """
        if isinstance(raw_node, dict):
            for k, v in raw_node.items():
                if k.endswith("Curie"):
                    # CURIEs are allowed in hand-edited source YAML, but they are
                    # intentionally resolved before writing JSON/YAML artifacts.
                    new_k = k[:-5]
                    processed_node[new_k] = self.resolve_curie(v)
                    del processed_node[k]
                elif k == "$ref" and v.startswith("#/") and self.imported:
                    if self.root_schema_fp is None:
                        msg = "Imported schema processor is missing a root schema path."
                        raise ValueError(msg)

                    # Keep imported local refs relative to the root schema output
                    # tree so split artifacts can still resolve sibling outputs.
                    rel_root = self.schema_fp.parent.relative_to(self.root_schema_fp.parent, walk_up=True)
                    schema_stem = self.schema_fp.stem.split("-")[0]
                    processed_node[k] = str(rel_root / f"{schema_stem}.json{v}")
                else:
                    self.resolve_property_tree_refs(raw_node[k], processed_node[k])
        elif isinstance(raw_node, list):
            for raw_item, processed_item in zip(raw_node, processed_node):
                self.resolve_property_tree_refs(raw_item, processed_item)
        return

    def get_class_definition(
        self, schema_class: str, raw: bool = False
    ) -> tuple[dict[str, Any], "YamlSchemaProcessor"]:
        """Get a local or imported class definition.

        Example:
            ``"vrs:Allele"`` returns the ``Allele`` definition from the imported
            ``vrs`` processor; ``"Allele"`` returns the local definition.

        :param schema_class: Local class name or CURIE-qualified class name.
        :param raw: When ``True``, return the raw source definition.
        :return: Class definition and processor that owns it.
        :raises ValueError: If ``schema_class`` is not local or CURIE-qualified.
        """
        components = schema_class.split(":")
        if len(components) == 1:
            inherited_class_name = components[0]
            if raw:
                inherited_class = self.raw_schema[self.schema_def_keyword][inherited_class_name]
            else:
                self.process_schema_class(inherited_class_name)
                inherited_class = self.processed_schema[self.schema_def_keyword][inherited_class_name]
            proc = self
        elif len(components) == 2:
            inherited_class_name = components[1]
            proc = self.imports[components[0]]
            if raw:
                inherited_class = proc.raw_schema[proc.schema_def_keyword][inherited_class_name]
            else:
                inherited_class = proc.processed_schema[proc.schema_def_keyword][inherited_class_name]
        else:
            msg = f"Expected local or CURIE-qualified class name, got {schema_class}."
            raise ValueError(msg)
        return inherited_class, proc

    def get_class_uri(self, schema_class: str, mode: str) -> str:
        """Get the absolute URI for a generated class artifact.

        :param schema_class: Class name to resolve.
        :param mode: Output mode, either ``json`` or ``yaml``.
        :return: Absolute class URI.
        :raises ValueError: If ``mode`` is not supported.
        """
        abs_path = self.get_class_abs_path(schema_class, mode)
        parsed_url = urlparse(self.id)
        return f"{parsed_url.scheme}://{parsed_url.netloc}{abs_path}"

    def get_class_abs_path(self, schema_class: str, mode: str) -> str:
        """Get the absolute URL path for a generated class artifact.

        :param schema_class: Class name to resolve.
        :param mode: Output mode, either ``json`` or ``yaml``.
        :return: Absolute URL path without scheme or host.
        :raises ValueError: If ``mode`` is not ``json`` or ``yaml``.
        """
        if mode == "json":
            export_key = self.json_key
        elif mode == "yaml":
            export_key = self.yaml_key
        else:
            msg = "mode must be json or yaml"
            raise ValueError(msg)
        if self.class_is_protected(schema_class):
            frag_containing_class = self.raw_defs[schema_class]["protectedClassOf"]
            class_ref = f"{frag_containing_class}#/{self.schema_def_keyword}/{schema_class}"
        else:
            class_ref = schema_class
        parsed_url = urlparse(self.id)
        parsed_id_path = parsed_url.path
        revised_path = Path(parsed_id_path).parent.joinpath(export_key, class_ref)
        return str(revised_path)

    def _validate_class_maturity(self, schema_class: str, class_def: dict[str, Any]) -> None:
        """Validate that a class declares a supported GKS maturity level.

        :param schema_class: Class name being processed.
        :param class_def: Processed class definition.
        :raises ValueError: If the class is missing maturity or uses an unknown value.
        """
        if "maturity" not in class_def:
            msg = f"{schema_class} is missing a maturity value."
            raise ValueError(msg)

        if class_def["maturity"] not in maturity_levels:
            msg = f"{schema_class} has unsupported maturity {class_def['maturity']}."
            raise ValueError(msg)

    def _track_protected_class(self, schema_class: str) -> None:
        """Record protected class membership for its containing class descendants.

        Adds entries to ``self.protected_classes_by_container``.

        :param schema_class: Protected class name to register.
        """
        containing_class = self.raw_defs[schema_class]["protectedClassOf"]
        self.protected_classes_by_container[containing_class].add(schema_class)
        if containing_class not in self.child_classes_by_parent:
            return

        for descendant in self.get_all_descendants(containing_class):
            self.protected_classes_by_container[descendant].add(schema_class)

    def _inherit_class_details(self, schema_class: str, class_def: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
        """Collect inherited property and required-field definitions.

        :param schema_class: Class name being processed.
        :param class_def: Processed class definition. Its ``ga4gh`` metadata may
            be added or merged when inherited identifier metadata applies.
        :return: Copied inherited properties and inherited required field names.
        :raises ValueError: If a concrete class inherits GA4GH metadata without
            defining its own prefix.
        """
        inherits = class_def.get("inherits")
        if inherits is None:
            return {}, set()

        inherited_class, _ = self.get_class_definition(inherits)
        inherited_properties = copy.deepcopy(inherited_class["heritableProperties"])
        inherited_required = set(inherited_class.get("heritableRequired", []))

        # GA4GH identifier metadata is inherited only for abstract pass-throughs.
        # Concrete classes must declare their own prefix so identifiers are stable.
        if "ga4gh" in class_def or "ga4gh" in inherited_class:
            if "ga4gh" not in class_def:
                if not self.class_is_abstract(schema_class):
                    msg = f"{schema_class} is missing a defined prefix."
                    raise ValueError(msg)

                class_def["ga4gh"] = copy.deepcopy(inherited_class["ga4gh"])
            elif "ga4gh" in inherited_class:
                inherent_fields = set(inherited_class["ga4gh"]["inherent"])
                inherent_fields |= set(class_def["ga4gh"].get("inherent", []))
                class_def["ga4gh"]["inherent"] = sorted(inherent_fields)

        return inherited_properties, inherited_required

    def _get_class_property_keys(self, schema_class: str) -> tuple[str, str]:
        """Get property and required keys for a class.

        :param schema_class: Class name being processed.
        :return: Property-map key and required-list key.
        """
        if self.class_is_abstract(schema_class):
            return "heritableProperties", "heritableRequired"

        return "properties", "required"

    def _process_container_refs(self, raw_class_def: dict[str, Any], processed_class_def: dict[str, Any]) -> None:
        """Resolve refs in an abstract container's child list.

        :param raw_class_def: Raw source class definition.
        :param processed_class_def: Processed class definition whose container
            ref list is rewritten.
        """
        for container_key in ("anyOf", "oneOf", "allOf"):
            if container_key in raw_class_def:
                self.resolve_property_tree_refs(raw_class_def[container_key], processed_class_def[container_key])
                return

    @staticmethod
    def _remove_conflicting_ref_shapes(inherited_property: dict[str, Any], prop_attribs: dict[str, Any]) -> None:
        """Remove inherited ref shapes replaced by local property attributes.

        :param inherited_property: Inherited property definition to update.
        :param prop_attribs: Local property attributes.
        """
        # Replacing an inherited union with a direct ref, or the reverse, should
        # leave only the local reference shape in the merged property.
        if "$ref" in prop_attribs:
            inherited_property.pop("oneOf", None)
            inherited_property.pop("anyOf", None)
        if "oneOf" in prop_attribs or "anyOf" in prop_attribs:
            inherited_property.pop("$ref", None)

    def _get_extended_property(
        self, schema_class: str, prop: str, prop_attribs: dict[str, Any], state: ClassProcessingState
    ) -> tuple[str, dict[str, Any]]:
        """Get the inherited property referenced by ``extends``.

        :param schema_class: Class name being processed.
        :param prop: Local property name.
        :param prop_attribs: Local property attributes.
        :param state: Class processing state.
        :return: Extended property name and inherited property definition.
        :raises ValueError: If ``extends`` references an unknown inherited property.
        """
        extended_property = prop_attribs["extends"]
        if extended_property not in state.inherited_properties:
            msg = f"{schema_class}.{prop} extends unknown inherited property {extended_property}."
            raise ValueError(msg)

        return extended_property, state.inherited_properties[extended_property]

    def _apply_property_extends(
        self,
        schema_class: str,
        prop: str,
        prop_attribs: dict[str, Any],
        state: ClassProcessingState,
    ) -> None:
        """Merge an inherited property extension into local properties.

        :param schema_class: Class name being processed.
        :param prop: Local property name.
        :param prop_attribs: Local property attributes.
        :param state: Class processing state. The extended property is removed
            from ``state.inherited_properties`` and may add ``prop`` to
            ``state.class_required``.
        :raises ValueError: If ``extends`` references an unknown inherited property.
        """
        extended_property, inherited_property = self._get_extended_property(schema_class, prop, prop_attribs, state)
        self._remove_conflicting_ref_shapes(inherited_property, prop_attribs)

        state.class_properties[prop] = inherited_property
        state.class_properties[prop].update(prop_attribs)
        state.class_properties[prop].pop("extends")
        state.inherited_properties.pop(extended_property)

        if extended_property in state.inherited_required:
            state.inherited_required.remove(extended_property)
            state.class_required.add(prop)

    def _validate_property(self, schema_class: str, prop: str, prop_attribs: dict[str, Any]) -> None:
        """Validate one processed property definition.

        :param schema_class: Class name that owns the property.
        :param prop: Property name.
        :param prop_attribs: Processed property attributes.
        :raises ValueError: If required strict-mode property metadata is invalid.
        """
        if self.enforce_ordered and prop_attribs.get("type", "") == "array":
            if "ordered" not in prop_attribs:
                msg = f"{schema_class}.{prop} missing ordered attribute."
                raise ValueError(msg)

            if not isinstance(prop_attribs["ordered"], bool):
                msg = f"{schema_class}.{prop} ordered attribute must be a boolean."
                raise ValueError(msg)

        if self.strict and prop_attribs.get("type", "") == "object":
            if prop_attribs.get("additionalProperties", None) is None:
                msg = f'"additionalProperties" expected to be defined in {schema_class}.{prop}'
                raise ValueError(msg)

    def _merge_and_validate_properties(
        self,
        schema_class: str,
        state: ClassProcessingState,
    ) -> None:
        """Merge inherited property extensions and validate processed properties.

        :param schema_class: Class name being processed.
        :param state: Class processing state. Extended properties are moved from
            inherited collections into local class collections.
        :raises ValueError: If property extensions or strict-mode metadata are invalid.
        """
        for prop, prop_attribs in state.class_properties.items():
            if "extends" in prop_attribs:
                self._apply_property_extends(
                    schema_class,
                    prop,
                    prop_attribs,
                    state,
                )

            self._validate_property(schema_class, prop, prop_attribs)

    def _validate_ga4gh_identifier(self, schema_class: str, class_def: dict[str, Any]) -> None:
        """Validate GA4GH identifier metadata for an identifiable class.

        :param schema_class: Class name being processed.
        :param class_def: Processed class definition.
        :raises ValueError: If ``ga4gh.prefix`` or inherent fields are invalid.
        """
        if not isinstance(class_def["ga4gh"]["prefix"], str):
            msg = f"{schema_class} ga4gh.prefix must be a string."
            raise ValueError(msg)

        if class_def["ga4gh"]["prefix"] == "":
            msg = f"{schema_class} ga4gh.prefix cannot be empty."
            raise ValueError(msg)

        inherent_count = len(class_def["ga4gh"]["inherent"])
        if inherent_count < 2:
            msg = (
                "GA4GH identifiable objects are expected to be defined by "
                f"at least 2 properties, {schema_class} has {inherent_count}."
            )
            raise ValueError(msg)

        if "type" not in class_def["ga4gh"]["inherent"]:
            msg = (
                "GA4GH identifiable objects are expected to include the class "
                f"type but not included for {schema_class}."
            )
            raise ValueError(msg)

    def _validate_class_structure(self, schema_class: str, class_def: dict[str, Any]) -> None:
        """Validate abstract/concrete class structure.

        :param schema_class: Class name being processed.
        :param class_def: Processed class definition.
        :raises ValueError: If the class has an invalid abstract or concrete shape.
        """
        if self.class_is_abstract(schema_class):
            if "type" in class_def:
                msg = f"{schema_class} is abstract and should not define type."
                raise ValueError(msg)
            return

        if "type" not in class_def:
            msg = f"{schema_class} is missing type."
            raise ValueError(msg)

        if class_def["type"] != "object":
            msg = f"{schema_class} type must be object."
            raise ValueError(msg)

        if self.class_is_ga4gh_identifiable(schema_class):
            self._validate_ga4gh_identifier(schema_class, class_def)

    def _get_class_processing_state(
        self, schema_class: str, class_def: dict[str, Any], property_key: str, required_key: str
    ) -> ClassProcessingState:
        """Build mutable processing state for one class.

        :param schema_class: Class name being processed.
        :param class_def: Processed class definition.
        :param property_key: Property-map key for the class.
        :param required_key: Required-list key for the class.
        :return: Class processing state.
        :raises ValueError: If inherited GA4GH metadata is invalid.
        """
        inherited_properties, inherited_required = self._inherit_class_details(schema_class, class_def)
        return ClassProcessingState(
            inherited_properties=inherited_properties,
            inherited_required=inherited_required,
            class_properties=class_def.get(property_key, {}),
            class_required=set(class_def.get(required_key, [])),
        )

    def _finalize_processed_class(
        self,
        schema_class: str,
        class_def: dict[str, Any],
        state: ClassProcessingState,
        property_key: str,
        required_key: str,
    ) -> None:
        """Write processed class state back to the class definition.

        :param schema_class: Class name being processed.
        :param class_def: Processed class definition to update.
        :param state: Final class processing state.
        :param property_key: Property-map key for the class.
        :param required_key: Required-list key for the class.
        """
        class_def[property_key] = state.inherited_properties | state.class_properties
        class_def[required_key] = sorted(state.inherited_required | state.class_required)
        if self.strict and not self.class_is_abstract(schema_class):
            class_def["additionalProperties"] = False
        self.processed_classes.add(schema_class)

    def _resolve_class_refs(
        self,
        schema_class: str,
        raw_class_def: dict[str, Any],
        processed_class_def: dict[str, Any],
        state: ClassProcessingState,
        property_key: str,
    ) -> None:
        """Resolve property and container refs for one class.

        :param schema_class: Class name being processed.
        :param raw_class_def: Raw source class definition.
        :param processed_class_def: Processed class definition to update.
        :param state: Class processing state containing local class properties.
        :param property_key: Property-map key for the class.
        """
        raw_class_properties = raw_class_def.get(property_key, {})
        self.resolve_property_tree_refs(raw_class_properties, state.class_properties)
        if self.class_is_container(schema_class):
            self._process_container_refs(raw_class_def, processed_class_def)

    def process_schema_class(self, schema_class: str) -> None:
        """Process and validate one schema class definition.

        This resolves inherited properties, rewrites CURIE refs, applies strict-mode
        object and array checks, and validates GA4GH identifier metadata.

        Example:
            A class with ``inherits: Entity`` receives inherited properties before
            its local ``properties`` are written to ``processed_schema``.

        :param schema_class: Class name under the schema ``$defs`` or
            ``definitions`` mapping.
        :raises ValueError: If the class violates required MSP schema structure.
        """
        raw_class_def = self.raw_schema[self.schema_def_keyword][schema_class]
        if schema_class in self.processed_classes:
            return
        processed_class_def = self.processed_schema[self.schema_def_keyword][schema_class]

        self._validate_class_maturity(schema_class, processed_class_def)

        if self.class_is_protected(schema_class):
            self._track_protected_class(schema_class)

        if self.class_is_primitive(schema_class):
            self.processed_classes.add(schema_class)
            return

        property_key, required_key = self._get_class_property_keys(schema_class)
        state = self._get_class_processing_state(schema_class, processed_class_def, property_key, required_key)

        self._resolve_class_refs(schema_class, raw_class_def, processed_class_def, state, property_key)
        self._merge_and_validate_properties(schema_class, state)
        self._validate_class_structure(schema_class, processed_class_def)
        self._finalize_processed_class(schema_class, processed_class_def, state, property_key, required_key)

    @staticmethod
    def _scrub_rst_markup(string: str) -> str:
        """Remove RST-only markup from schema descriptions.

        :param string: Description text that may contain RST roles or links.
        :return: Plain Markdown-like text safe for JSON Schema descriptions.
        """
        string = ref_re.sub(r"\g<1>", string)
        string = link_re.sub(r"[\g<1>](\g<2>)", string)
        string = string.replace("\n", " ")
        return string

    def clean_for_js(self) -> None:
        """Remove MSP-only metadata and expand abstract refs for JSON Schema output."""
        self.for_js.pop("namespaces", None)
        self.for_js.pop("strict", None)
        self.for_js.pop("enforce_ordered", None)
        self.for_js.pop("imports", None)
        abstract_class_removals = []
        for schema_class, schema_definition in self.for_js.get(self.schema_def_keyword, {}).items():
            should_remove = self._clean_schema_definition_for_js(schema_class, schema_definition)
            if should_remove:
                abstract_class_removals.append(schema_class)

        for schema_class in abstract_class_removals:
            self.for_js[self.schema_def_keyword].pop(schema_class)

    def _clean_schema_definition_for_js(self, schema_class: str, schema_definition: dict[str, Any]) -> bool:
        """Clean one class definition for JSON Schema output.

        :param schema_class: Class name being cleaned.
        :param schema_definition: JS output definition. MSP-only keys and RST
            markup are removed from this mapping.
        :return: ``True`` when an empty abstract definition should be removed.
        """
        schema_definition.pop("inherits", None)
        schema_definition.pop("protectedClassOf", None)

        if self.class_is_abstract(schema_class):
            self._clean_abstract_definition_for_js(schema_definition)
            if not any(key in schema_definition for key in ("oneOf", "allOf", "$ref")):
                return True

        self._scrub_schema_definition_descriptions(schema_definition)
        return False

    def _clean_abstract_definition_for_js(self, schema_definition: dict[str, Any]) -> None:
        """Remove abstract-only metadata and expand refs for one JS definition.

        :param schema_definition: Abstract JS output definition to update.
        """
        schema_definition.pop("heritableProperties", None)
        schema_definition.pop("heritableRequired", None)
        schema_definition.pop("ga4gh", None)
        schema_definition.pop("header_level", None)
        self.expand_abstract_refs(schema_definition)

    def _scrub_schema_definition_descriptions(self, schema_definition: dict[str, Any]) -> None:
        """Remove RST markup from a JS definition and its properties.

        :param schema_definition: JS output definition to update.
        """
        if "description" in schema_definition:
            schema_definition["description"] = self._scrub_rst_markup(schema_definition["description"])
        if "properties" not in schema_definition:
            return

        for property_definition in schema_definition["properties"].values():
            if "description" in property_definition:
                property_definition["description"] = self._scrub_rst_markup(property_definition["description"])
            self.expand_abstract_refs(property_definition)

    def expand_abstract_refs(self, js_obj: dict[str, Any]) -> None:
        """Replace abstract class refs with concrete descendant refs.

        :param js_obj: JSON Schema node. Abstract ``$ref`` and ``oneOf`` entries
            are replaced on this mapping.
        """
        if "$ref" in js_obj:
            descendents = self.get_concrete_class_refs(js_obj["$ref"])
            if descendents != {js_obj["$ref"]}:
                js_obj.pop("$ref")
                js_obj["oneOf"] = self._build_ref_list(descendents)
        elif "oneOf" in js_obj:
            # do the same check for each member
            ref_list = js_obj["oneOf"]
            descendents = set()
            inlined = []
            for ref in ref_list:
                if "$ref" not in ref:
                    inlined.append(ref)
                else:
                    descendents.update(self.get_concrete_class_refs(ref["$ref"]))
            js_obj["oneOf"] = self._build_ref_list(descendents) + inlined
        elif js_obj.get("type", "") == "array":
            self.expand_abstract_refs(js_obj["items"])

    def get_concrete_class_refs(self, cls_url: str) -> set[str]:
        """Resolve a class ref to concrete descendant class refs.

        :param cls_url: Local class reference URL.
        :return: Concrete class reference URLs.
        """
        children = self.child_ref_urls_by_parent_ref.get(cls_url, None)
        if children is None:
            return {cls_url}
        out = set()
        for child in children:
            out.update(self.get_concrete_class_refs(child))
        return out

    @staticmethod
    def _build_ref_list(cls_urls: set[str]) -> list[dict[str, str]]:
        """Build a sorted JSON Schema ``$ref`` list.

        :param cls_urls: Class reference URLs.
        :return: Sorted list of ``{"$ref": url}`` mappings.
        """
        return [{"$ref": url} for url in sorted(cls_urls)]
