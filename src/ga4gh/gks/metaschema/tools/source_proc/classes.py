"""Class-processing helpers for source schema processing."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ga4gh.gks.metaschema.tools.source_proc.graph import (
    class_is_abstract,
    class_is_container,
    class_is_ga4gh_identifiable,
    class_is_primitive,
    class_is_protected,
    get_all_descendants,
    get_class_definition,
)
from ga4gh.gks.metaschema.tools.source_proc.paths import (
    resolve_property_tree_refs,
)
from ga4gh.gks.metaschema.tools.source_proc.properties import (
    merge_and_validate_properties,
)

if TYPE_CHECKING:
    from ga4gh.gks.metaschema.tools.source_proc.processor import YamlSchemaProcessor


MATURITY_LEVELS = {"deprecated": 0, "draft": 1, "trial use": 2, "normative": 3}


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


def process_schema_class(processor: YamlSchemaProcessor, schema_class: str) -> None:
    """Process and validate one schema class definition.

    Example:
        A class with ``inherits: Entity`` is processed by copying inherited
        properties into working state, resolving local refs and CURIEs, applying
        any property ``extends`` rules, and then writing the final property map
        back to the processed schema.

    :param processor: Owning schema processor.
    :param schema_class: Class name under the schema definitions mapping.
    :raises ValueError: If the class violates required MSP schema structure.

    """
    if schema_class in processor.processed_classes:
        return

    raw_class_def = processor.raw_schema[processor.schema_def_keyword][schema_class]
    processed_class_def = processor.processed_schema[processor.schema_def_keyword][
        schema_class
    ]
    _validate_class_maturity(schema_class, processed_class_def)

    if class_is_protected(processor, schema_class):
        _track_protected_class(processor, schema_class)

    if class_is_primitive(processor, schema_class):
        processor.processed_classes.add(schema_class)
        return

    property_key, required_key = _get_class_property_keys(processor, schema_class)
    state = _build_class_processing_state(
        processor, schema_class, processed_class_def, property_key, required_key
    )
    _resolve_class_refs(
        processor,
        schema_class,
        raw_class_def,
        processed_class_def,
        state,
        property_key,
    )
    merge_and_validate_properties(processor, schema_class, state)
    _validate_class_structure(processor, schema_class, processed_class_def)
    _finalize_processed_class(
        processor, schema_class, processed_class_def, state, property_key, required_key
    )


def _validate_class_maturity(schema_class: str, class_def: dict[str, Any]) -> None:
    """Validate that a class declares a supported GKS maturity level.

    :param schema_class: Class name being processed.
    :param class_def: Processed class definition.
    :raises ValueError: If the maturity field is missing or unsupported.
    """
    if "maturity" not in class_def:
        msg = f"{schema_class} is missing a maturity value."
        raise ValueError(msg)

    if class_def["maturity"] not in MATURITY_LEVELS:
        msg = f"{schema_class} has unsupported maturity {class_def['maturity']}."
        raise ValueError(msg)


def _track_protected_class(processor: YamlSchemaProcessor, schema_class: str) -> None:
    """Record protected class membership for containing-class descendants.

    :param processor: Owning schema processor.
    :param schema_class: Protected class name to register.
    """
    containing_class = processor.raw_defs[schema_class]["protectedClassOf"]
    processor.protected_classes_by_container[containing_class].add(schema_class)
    if containing_class not in processor.child_classes_by_parent:
        return

    for descendant in get_all_descendants(processor, containing_class):
        processor.protected_classes_by_container[descendant].add(schema_class)


def _get_class_property_keys(
    processor: YamlSchemaProcessor, schema_class: str
) -> tuple[str, str]:
    """Return property and required keys for a class.

    :param processor: Owning schema processor.
    :param schema_class: Class name being processed.
    :return: Property-map key and required-list key.
    """
    if class_is_abstract(processor, schema_class):
        return "heritableProperties", "heritableRequired"
    return "properties", "required"


def _build_class_processing_state(
    processor: YamlSchemaProcessor,
    schema_class: str,
    class_def: dict[str, Any],
    property_key: str,
    required_key: str,
) -> ClassProcessingState:
    """Build mutable processing state for one class.

    :param processor: Owning schema processor.
    :param schema_class: Class name being processed.
    :param class_def: Processed class definition.
    :param property_key: Property-map key for the class.
    :param required_key: Required-list key for the class.
    :return: Class processing state.
    """
    inherited_properties, inherited_required = _inherit_class_details(
        processor, schema_class, class_def
    )
    return ClassProcessingState(
        inherited_properties=inherited_properties,
        inherited_required=inherited_required,
        class_properties=class_def.get(property_key, {}),
        class_required=set(class_def.get(required_key, [])),
    )


def _inherit_class_details(
    processor: YamlSchemaProcessor, schema_class: str, class_def: dict[str, Any]
) -> tuple[dict[str, Any], set[str]]:
    """Collect inherited property and required-field definitions.

    :param processor: Owning schema processor.
    :param schema_class: Class name being processed.
    :param class_def: Processed class definition, updated in place when GA4GH
        metadata must be inherited.
    :return: Copied inherited properties and inherited required field names.
    :raises ValueError: If a concrete class inherits GA4GH metadata without
        defining its own prefix.
    """
    inherits = class_def.get("inherits")
    if inherits is None:
        return {}, set()

    inherited_class, _ = get_class_definition(processor, inherits)
    inherited_properties = copy.deepcopy(inherited_class["heritableProperties"])
    inherited_required = set(inherited_class.get("heritableRequired", []))

    if "ga4gh" in class_def or "ga4gh" in inherited_class:
        if "ga4gh" not in class_def:
            if not class_is_abstract(processor, schema_class):
                msg = f"{schema_class} is missing a defined prefix."
                raise ValueError(msg)
            class_def["ga4gh"] = copy.deepcopy(inherited_class["ga4gh"])
        elif "ga4gh" in inherited_class:
            inherent_fields = set(inherited_class["ga4gh"]["inherent"])
            inherent_fields |= set(class_def["ga4gh"].get("inherent", []))
            class_def["ga4gh"]["inherent"] = sorted(inherent_fields)

    return inherited_properties, inherited_required


def _resolve_class_refs(
    processor: YamlSchemaProcessor,
    schema_class: str,
    raw_class_def: dict[str, Any],
    processed_class_def: dict[str, Any],
    state: ClassProcessingState,
    property_key: str,
) -> None:
    """Resolve property and container refs for one class.

    :param processor: Owning schema processor.
    :param schema_class: Class name being processed.
    :param raw_class_def: Raw source class definition.
    :param processed_class_def: Processed class definition to update.
    :param state: Class processing state.
    :param property_key: Property-map key for the class.
    """
    raw_class_properties = raw_class_def.get(property_key, {})
    resolve_property_tree_refs(processor, raw_class_properties, state.class_properties)
    if not class_is_container(processor, schema_class):
        return

    for container_key in ("anyOf", "oneOf", "allOf"):
        if container_key in raw_class_def:
            resolve_property_tree_refs(
                processor,
                raw_class_def[container_key],
                processed_class_def[container_key],
            )
            return


def _validate_class_structure(
    processor: YamlSchemaProcessor, schema_class: str, class_def: dict[str, Any]
) -> None:
    """Validate abstract/concrete class structure.

    :param processor: Owning schema processor.
    :param schema_class: Class name being processed.
    :param class_def: Processed class definition.
    :raises ValueError: If the class has an invalid abstract or concrete shape.
    """
    if class_is_abstract(processor, schema_class):
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
    if class_is_ga4gh_identifiable(processor, schema_class):
        _validate_ga4gh_identifier(schema_class, class_def)


def _validate_ga4gh_identifier(schema_class: str, class_def: dict[str, Any]) -> None:
    """Validate GA4GH identifier metadata for an identifiable class.

    :param schema_class: Class name being processed.
    :param class_def: Processed class definition.
    :raises TypeError: If ``ga4gh.prefix`` is not a string.
    :raises ValueError: If ``ga4gh.prefix`` or inherent fields are invalid.
    """
    if not isinstance(class_def["ga4gh"]["prefix"], str):
        msg = f"{schema_class} ga4gh.prefix must be a string."
        raise TypeError(msg)
    if class_def["ga4gh"]["prefix"] == "":
        msg = f"{schema_class} ga4gh.prefix cannot be empty."
        raise ValueError(msg)

    inherent_count = len(class_def["ga4gh"]["inherent"])
    if inherent_count < 2:  # noqa: PLR2004
        msg = (
            "GA4GH identifiable objects are expected to be defined by at least "
            f"2 properties, {schema_class} has {inherent_count}."
        )
        raise ValueError(msg)
    if "type" not in class_def["ga4gh"]["inherent"]:
        msg = f"GA4GH identifiable objects are expected to include the class type but not included for {schema_class}."
        raise ValueError(msg)


def _finalize_processed_class(
    processor: YamlSchemaProcessor,
    schema_class: str,
    class_def: dict[str, Any],
    state: ClassProcessingState,
    property_key: str,
    required_key: str,
) -> None:
    """Write processed class state back to the class definition.

    :param processor: Owning schema processor.
    :param schema_class: Class name being processed.
    :param class_def: Processed class definition updated in place.
    :param state: Final class processing state.
    :param property_key: Property-map key for the class.
    :param required_key: Required-list key for the class.
    """
    class_def[property_key] = state.inherited_properties | state.class_properties
    class_def[required_key] = sorted(state.inherited_required | state.class_required)
    if processor.strict and not class_is_abstract(processor, schema_class):
        class_def["additionalProperties"] = False
    processor.processed_classes.add(schema_class)
