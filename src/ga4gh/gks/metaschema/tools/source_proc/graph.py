"""Class graph and query helpers for source schema processing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ga4gh.gks.metaschema.tools.source_proc.paths import resolve_curie

if TYPE_CHECKING:
    from ga4gh.gks.metaschema.tools.source_proc.processor import YamlSchemaProcessor


def get_class_definition(
    processor: YamlSchemaProcessor, schema_class: str, raw: bool = False
) -> tuple[dict[str, Any], YamlSchemaProcessor]:
    """Return a local or imported class definition.

    Example:
        ``"vrs:Allele"`` returns the imported ``Allele`` definition owned by the
        ``vrs`` processor, while ``"Allele"`` returns the local definition from
        ``processor``.

    :param processor: Owning schema processor.
    :param schema_class: Local class name or CURIE-qualified class name.
    :param raw: When ``True``, return the raw source definition.
    :return: Class definition and the processor that owns it.
    :raises ValueError: If ``schema_class`` is not local or CURIE-qualified.

    """
    components = schema_class.split(":")
    if len(components) == 1:
        class_name = components[0]
        schema = processor.raw_schema if raw else processor.processed_schema
        return schema[processor.schema_def_keyword][class_name], processor

    if len(components) == 2:  # noqa: PLR2004
        alias, class_name = components
        imported_processor = processor.imports[alias]
        schema = (
            imported_processor.raw_schema
            if raw
            else imported_processor.processed_schema
        )
        return schema[imported_processor.schema_def_keyword][
            class_name
        ], imported_processor

    msg = f"Expected local or CURIE-qualified class name, got {schema_class}."
    raise ValueError(msg)


def build_class_relationship_maps(processor: YamlSchemaProcessor) -> None:
    """Build class inheritance and container-child lookup maps.

    :param processor: Owning schema processor.
    """
    for schema_class, class_def in processor.raw_defs.items():
        class_ref = f"#/{processor.schema_def_keyword}/{schema_class}"
        if class_is_container(processor, schema_class):
            _register_container_children(processor, schema_class, class_ref, class_def)
        if "inherits" in class_def:
            _register_inherited_child(
                processor, schema_class, class_ref, class_def["inherits"]
            )


def get_all_descendants(processor: YamlSchemaProcessor, cls: str) -> set[str]:
    """Return all classes that descend from ``cls``.

    :param processor: Owning schema processor.
    :param cls: Class name to inspect.
    :return: Descendant class names.
    """
    descendants: set[str] = set()
    for child in processor.child_classes_by_parent.get(cls, []):
        descendants.add(child)
        descendants.update(get_all_descendants(processor, child))
    return descendants


def check_processed_schema(processor: YamlSchemaProcessor) -> None:
    """Validate parent/child maturity relationships after processing.

    :param processor: Owning schema processor.
    :raises ValueError: If inherited classes are missing maturity values or a
        child class has greater maturity than its parent.
    """
    for schema_class in processor.processed_classes:
        class_def = processor.defs[schema_class]
        inherits = class_def.get("inherits")
        if inherits is None:
            continue

        inherited_class_def = _get_inherited_class_def(processor, inherits)
        _validate_maturity_pair(schema_class, class_def, inherits, inherited_class_def)


def class_is_abstract(processor: YamlSchemaProcessor, schema_class: str) -> bool:
    """Return whether a schema class is abstract.

    :param processor: Owning schema processor.
    :param schema_class: Class name to inspect.
    :return: ``True`` when the class has no concrete properties and is not primitive.
    """
    class_def, _ = get_class_definition(processor, schema_class, raw=True)
    return "properties" not in class_def and not class_is_primitive(
        processor, schema_class
    )


def class_is_container(processor: YamlSchemaProcessor, schema_class: str) -> bool:
    """Return whether a schema class is an abstract container.

    :param processor: Owning schema processor.
    :param schema_class: Class name to inspect.
    :return: ``True`` when the class enumerates children with ``oneOf``, ``anyOf``,
        or ``allOf``.
    """
    class_def, _ = get_class_definition(processor, schema_class, raw=True)
    return class_is_abstract(processor, schema_class) and any(
        key in class_def for key in ("oneOf", "anyOf", "allOf")
    )


def class_is_ga4gh_identifiable(
    processor: YamlSchemaProcessor, schema_class: str
) -> bool:
    """Return whether a class declares GA4GH identifier metadata.

    :param processor: Owning schema processor.
    :param schema_class: Class name to inspect.
    :return: ``True`` when the class has a ``ga4gh.prefix`` value.
    """
    class_def, _ = get_class_definition(processor, schema_class, raw=True)
    return "ga4gh" in class_def and "prefix" in class_def["ga4gh"]


def class_is_protected(processor: YamlSchemaProcessor, schema_class: str) -> bool:
    """Return whether a class is protected under another class.

    :param processor: Owning schema processor.
    :param schema_class: Class name to inspect.
    :return: ``True`` when the class declares ``protectedClassOf``.
    """
    class_def, _ = get_class_definition(processor, schema_class, raw=True)
    return "protectedClassOf" in class_def


def class_is_passthrough(processor: YamlSchemaProcessor, schema_class: str) -> bool:
    """Return whether an abstract class only passes through an inherited class.

    :param processor: Owning schema processor.
    :param schema_class: Class name to inspect.
    :return: ``True`` when the class inherits without defining local property maps.
    """
    if not class_is_abstract(processor, schema_class):
        return False

    class_def, _ = get_class_definition(processor, schema_class, raw=True)
    return (
        "heritableProperties" not in class_def
        and "properties" not in class_def
        and bool(class_def.get("inherits", False))
    )


def class_is_primitive(processor: YamlSchemaProcessor, schema_class: str) -> bool:
    """Return whether a class represents a primitive JSON Schema value.

    :param processor: Owning schema processor.
    :param schema_class: Class name to inspect.
    :return: ``True`` when the class type is neither ``abstract`` nor ``object``.
    """
    class_def, _ = get_class_definition(processor, schema_class, raw=True)
    return class_def.get("type", "abstract") not in ["abstract", "object"]


def class_is_subclass(
    processor: YamlSchemaProcessor, schema_class: str, parent_class: str
) -> bool:
    """Return whether a class descends from another class.

    :param processor: Owning schema processor.
    :param schema_class: Candidate child class name.
    :param parent_class: Candidate parent class name.
    :return: ``True`` when the child is reachable from the parent hierarchy.
    """
    child_ref = f"#/{processor.schema_def_keyword}/{schema_class}"
    parent_ref = f"#/{processor.schema_def_keyword}/{parent_class}"
    return child_ref in get_concrete_class_refs(processor, parent_ref)


def get_concrete_class_refs(processor: YamlSchemaProcessor, cls_url: str) -> set[str]:
    """Resolve a class ref to concrete descendant refs.

    :param processor: Owning schema processor.
    :param cls_url: Local class reference URL.
    :return: Concrete class reference URLs.
    """
    children = processor.child_ref_urls_by_parent_ref.get(cls_url)
    if children is None:
        return {cls_url}

    refs: set[str] = set()
    for child in children:
        refs.update(get_concrete_class_refs(processor, child))
    return refs


def _register_container_children(
    processor: YamlSchemaProcessor,
    schema_class: str,
    class_ref: str,
    class_def: dict[str, Any],
) -> None:
    """Register concrete children listed by an abstract container class.

    :param processor: Owning schema processor.
    :param schema_class: Container class name.
    :param class_ref: Local reference URL for the container class.
    :param class_def: Raw container class definition.
    """
    child_urls = processor.child_ref_urls_by_parent_ref.get(class_ref, set())
    child_classes = processor.child_classes_by_parent.get(schema_class, set())
    for record in _get_container_child_records(class_def):
        if not isinstance(record, dict):
            continue
        child_url = _get_child_ref(processor, record)
        child_urls.add(child_url)
        child_classes.add(child_url.split("/")[-1])

    processor.child_ref_urls_by_parent_ref[class_ref] = child_urls
    processor.child_classes_by_parent[schema_class] = child_classes


def _get_container_child_records(class_def: dict[str, Any]) -> list[dict[str, str]]:
    """Return child records from a container class definition.

    :param class_def: Raw container class definition.
    :return: Container child refs.
    """
    for key in ("oneOf", "anyOf", "allOf"):
        if key in class_def:
            return class_def[key]
    return [{"$ref": class_def["$ref"]}]


def _get_child_ref(processor: YamlSchemaProcessor, record: dict[str, str]) -> str:
    """Return the concrete child reference from a container record.

    :param processor: Owning schema processor.
    :param record: Container child record.
    :return: Concrete child reference.
    """
    if "$refCurie" in record:
        return resolve_curie(processor, record["$refCurie"])
    return record["$ref"]


def _register_inherited_child(
    processor: YamlSchemaProcessor, schema_class: str, class_ref: str, target: str
) -> None:
    """Register a class as a child of its local inherited parent.

    :param processor: Owning schema processor.
    :param schema_class: Child class name.
    :param class_ref: Local reference URL for the child class.
    :param target: Inherited class name or CURIE.
    """
    if ":" in target:
        return

    target_url = f"#/{processor.schema_def_keyword}/{target}"
    child_urls = processor.child_ref_urls_by_parent_ref.get(target_url, set())
    child_classes = processor.child_classes_by_parent.get(target, set())
    child_urls.add(class_ref)
    child_classes.add(schema_class)
    processor.child_ref_urls_by_parent_ref[target_url] = child_urls
    processor.child_classes_by_parent[target] = child_classes


def _get_inherited_class_def(
    processor: YamlSchemaProcessor, inherits: str
) -> dict[str, Any]:
    """Return the processed inherited class definition.

    :param processor: Owning schema processor.
    :param inherits: Inherited class name or CURIE.
    :return: Processed inherited class definition.
    """
    if ":" in inherits:
        alias, class_name = inherits.split(":")
        return processor.imports[alias].defs[class_name]
    return processor.defs[inherits]


def _validate_maturity_pair(
    schema_class: str,
    class_def: dict[str, Any],
    inherited_class_name: str,
    inherited_class_def: dict[str, Any],
) -> None:
    """Validate a processed class maturity against its inherited parent.

    :param schema_class: Child class name.
    :param class_def: Processed child class definition.
    :param inherited_class_name: Inherited class name or CURIE.
    :param inherited_class_def: Processed parent class definition.
    :raises ValueError: If maturity values are missing or out of order.
    """
    if "maturity" not in class_def:
        msg = f"{schema_class} is missing a maturity value."
        raise ValueError(msg)
    if "maturity" not in inherited_class_def:
        msg = f"{inherited_class_name} is missing a maturity value."
        raise ValueError(msg)
    if inherited_class_def["maturity"] < class_def["maturity"]:
        msg = f"Maturity of {schema_class} is greater than parent class {inherited_class_name}."
        raise ValueError(msg)
