"""Property-processing helpers for source schema processing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ga4gh.gks.metaschema.tools.source_proc.classes import ClassProcessingState
    from ga4gh.gks.metaschema.tools.source_proc.processor import YamlSchemaProcessor


def merge_and_validate_properties(
    processor: YamlSchemaProcessor,
    schema_class: str,
    state: ClassProcessingState,
) -> None:
    """Merge inherited property extensions and validate processed properties.

    :param processor: Owning schema processor.
    :param schema_class: Class name being processed.
    :param state: Class processing state updated in place.
    :raises ValueError: If property extensions or strict-mode metadata are invalid.
    """
    for prop, prop_attribs in state.class_properties.items():
        if "extends" in prop_attribs:
            apply_property_extends(schema_class, prop, prop_attribs, state)
        validate_property(processor, schema_class, prop, prop_attribs)


def apply_property_extends(
    schema_class: str,
    prop: str,
    prop_attribs: dict[str, Any],
    state: ClassProcessingState,
) -> None:
    """Merge an inherited property extension into local properties.

    Example:
        If ``name`` extends inherited property ``label``, the inherited property
        definition is copied to ``name``, local attributes override inherited
        values, and required-field tracking is moved from ``label`` to ``name``
        when needed.

    :param schema_class: Class name being processed.
    :param prop: Local property name.
    :param prop_attribs: Local property attributes.
    :param state: Class processing state updated in place.
    :raises ValueError: If ``extends`` references an unknown inherited property.

    """
    extended_property = prop_attribs["extends"]
    if extended_property not in state.inherited_properties:
        msg = f"{schema_class}.{prop} extends unknown inherited property {extended_property}."
        raise ValueError(msg)

    inherited_property = state.inherited_properties[extended_property]
    remove_conflicting_ref_shapes(inherited_property, prop_attribs)
    state.class_properties[prop] = inherited_property
    state.class_properties[prop].update(prop_attribs)
    state.class_properties[prop].pop("extends")
    state.inherited_properties.pop(extended_property)

    if extended_property in state.inherited_required:
        state.inherited_required.remove(extended_property)
        state.class_required.add(prop)


def remove_conflicting_ref_shapes(
    inherited_property: dict[str, Any], prop_attribs: dict[str, Any]
) -> None:
    """Remove inherited ref shapes replaced by local property attributes.

    :param inherited_property: Inherited property definition to update.
    :param prop_attribs: Local property attributes.
    """
    if "$ref" in prop_attribs:
        inherited_property.pop("oneOf", None)
        inherited_property.pop("anyOf", None)
    if "oneOf" in prop_attribs or "anyOf" in prop_attribs:
        inherited_property.pop("$ref", None)


def validate_property(
    processor: YamlSchemaProcessor,
    schema_class: str,
    prop: str,
    prop_attribs: dict[str, Any],
) -> None:
    """Validate one processed property definition.

    :param processor: Owning schema processor.
    :param schema_class: Class name that owns the property.
    :param prop: Property name.
    :param prop_attribs: Processed property attributes.
    :raises ValueError: If required strict-mode property metadata is invalid.
    """
    if processor.enforce_ordered and prop_attribs.get("type", "") == "array":
        if "ordered" not in prop_attribs:
            msg = f"{schema_class}.{prop} missing ordered attribute."
            raise ValueError(msg)
        if not isinstance(prop_attribs["ordered"], bool):
            msg = f"{schema_class}.{prop} ordered attribute must be a boolean."
            raise ValueError(msg)

    if (
        processor.strict
        and prop_attribs.get("type", "") == "object"
        and prop_attribs.get("additionalProperties") is None
    ):
        msg = f'"additionalProperties" expected to be defined in {schema_class}.{prop}'
        raise ValueError(msg)
