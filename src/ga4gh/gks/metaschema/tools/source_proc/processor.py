"""Core processor state for GKS source schema processing."""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, TextIO, cast

import yaml

from ga4gh.gks.metaschema.tools.source_proc import classes, config, imports, output
from ga4gh.gks.metaschema.tools.source_proc.graph import (
    build_class_relationship_maps,
    check_processed_schema,
    class_is_passthrough,
    class_is_primitive,
    class_is_protected,
    class_is_subclass,
    get_class_definition,
)
from ga4gh.gks.metaschema.tools.source_proc.paths import (
    get_class_abs_path,
    get_class_uri,
    load_schema,
)

SCHEMA_DEF_KEYWORD_BY_VERSION = {
    "https://json-schema.org/draft-07/schema": "definitions",
    "https://json-schema.org/draft/2020-12/schema": "$defs",
}


class YamlSchemaProcessor:
    """Process a GKS source YAML file into resolved schema artifacts.

    The processor owns schema state and exposes the small API used by the CLI
    scripts. Workflow logic lives in the sibling package modules.
    """

    def __init__(self, schema_fp: Path, root_fp: Path | None = None) -> None:
        """Initialize a source schema processor.

        :param schema_fp: Path to the source YAML schema.
        :param root_fp: Root source YAML path when processing an imported schema.
        """
        self.schema_fp = Path(schema_fp).resolve()
        self.imported = root_fp is not None
        self.root_schema_fp = Path(root_fp).resolve() if root_fp is not None else None
        self.raw_schema = load_schema(self.schema_fp)
        config.apply_metaschema_config(self)
        self.schema_def_keyword = SCHEMA_DEF_KEYWORD_BY_VERSION[cast("str", self.raw_schema["$schema"])]
        self.raw_defs = self.raw_schema.get(self.schema_def_keyword, None)
        self._namespaces = dict(self.raw_schema.get("namespaces", {}))
        self._yaml_fp_override: Path | None = None
        self._json_fp_override: Path | None = None
        self._def_fp_override: Path | None = None
        self.imports: dict[str, YamlSchemaProcessor] = {}
        imports.import_dependencies(self)
        self._rebuild_processed_state()

    @property
    def id(self) -> str:
        """Return the source schema identifier."""
        return cast("str", self.raw_schema["$id"])

    @property
    def yaml_key(self) -> str:
        """Return the YAML artifact directory name."""
        return cast("str", self.raw_schema.get("yaml-target", "yaml"))

    @property
    def json_key(self) -> str:
        """Return the JSON artifact directory name."""
        return cast("str", self.raw_schema.get("json-target", "json"))

    @property
    def defs_key(self) -> str:
        """Return the RST artifact directory name."""
        return cast("str", self.raw_schema.get("def-target", "def"))

    @property
    def yaml_fp(self) -> Path:
        """Return the YAML artifact directory."""
        return self._yaml_fp_override or (self.schema_fp.parent / self.yaml_key)

    @yaml_fp.setter
    def yaml_fp(self, value: Path) -> None:
        """Override the YAML artifact directory."""
        self._yaml_fp_override = Path(value)

    @property
    def json_fp(self) -> Path:
        """Return the JSON artifact directory."""
        return self._json_fp_override or (self.schema_fp.parent / self.json_key)

    @json_fp.setter
    def json_fp(self, value: Path) -> None:
        """Override the JSON artifact directory."""
        self._json_fp_override = Path(value)

    @property
    def def_fp(self) -> Path:
        """Return the RST artifact directory."""
        return self._def_fp_override or (self.schema_fp.parent / self.defs_key)

    @def_fp.setter
    def def_fp(self, value: Path) -> None:
        """Override the RST artifact directory."""
        self._def_fp_override = Path(value)

    @property
    def namespaces(self) -> dict[str, str]:
        """Return configured namespace mappings."""
        return self._namespaces

    @property
    def strict(self) -> bool:
        """Return whether strict schema validation is enabled."""
        return cast("bool", self.raw_schema.get("strict", False))

    @property
    def enforce_ordered(self) -> bool:
        """Return whether ordered property validation is enabled."""
        return cast("bool", self.raw_schema.get("enforce_ordered", self.strict))

    def _rebuild_processed_state(self) -> None:
        """Rebuild all processor-derived state from ``raw_schema``."""
        self.child_ref_urls_by_parent_ref = {}
        self.child_classes_by_parent = {}
        build_class_relationship_maps(self)
        self.protected_classes_by_container = defaultdict(set)
        self.processed_schema = copy.deepcopy(self.raw_schema)
        self.defs = self.processed_schema.get(self.schema_def_keyword, None)
        self.processed_classes: set[str] = set()
        self._process_schema()
        check_processed_schema(self)
        self.for_js = copy.deepcopy(self.processed_schema)
        output.clean_for_js(self)

    def _process_schema(self) -> None:
        """Process all class definitions in the current schema."""
        if self.defs is None:
            return
        for schema_class in self.defs:
            classes.process_schema_class(self, schema_class)

    def merge_imported_definitions(self) -> None:
        """Merge imported definitions into the current processor."""
        imports.merge_imported_definitions(self)

    def get_metaschema_config_fp(self) -> Path | None:
        """Return the owning ``metaschema.yaml`` path, if present."""
        return config.get_metaschema_config_fp(self)

    def get_class_definition(self, schema_class: str, raw: bool = False) -> tuple[dict[str, Any], YamlSchemaProcessor]:
        """Return a local or imported class definition.

        :param schema_class: Local class name or CURIE-qualified class name.
        :param raw: When ``True``, return the raw source definition.
        :return: Class definition and the processor that owns it.
        """
        return get_class_definition(self, schema_class, raw=raw)

    def get_class_uri(self, schema_class: str, mode: str) -> str:
        """Return the absolute URI for a generated class artifact.

        :param schema_class: Class name to resolve.
        :param mode: Output mode, either ``json`` or ``yaml``.
        :return: Absolute class URI.
        """
        return get_class_uri(self, schema_class, mode)

    def get_class_abs_path(self, schema_class: str, mode: str) -> str:
        """Return the absolute URL path for a generated class artifact.

        :param schema_class: Class name to resolve.
        :param mode: Output mode, either ``json`` or ``yaml``.
        :return: Absolute URL path without scheme or host.
        """
        return get_class_abs_path(self, schema_class, mode)

    def class_is_passthrough(self, schema_class: str) -> bool:
        """Return whether an abstract class only passes through an inherited class.

        :param schema_class: Class name to inspect.
        :return: ``True`` when the class inherits without defining local property maps.
        """
        return class_is_passthrough(self, schema_class)

    def class_is_primitive(self, schema_class: str) -> bool:
        """Return whether a class represents a primitive JSON Schema value.

        :param schema_class: Class name to inspect.
        :return: ``True`` when the class type is neither ``abstract`` nor ``object``.
        """
        return class_is_primitive(self, schema_class)

    def class_is_protected(self, schema_class: str) -> bool:
        """Return whether a class is protected under another class.

        :param schema_class: Class name to inspect.
        :return: ``True`` when the class declares ``protectedClassOf``.
        """
        return class_is_protected(self, schema_class)

    def class_is_subclass(self, schema_class: str, parent_class: str) -> bool:
        """Return whether a class descends from another class.

        :param schema_class: Candidate child class name.
        :param parent_class: Candidate parent class name.
        :return: ``True`` when the child is reachable from the parent hierarchy.
        """
        return class_is_subclass(self, schema_class, parent_class)

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
