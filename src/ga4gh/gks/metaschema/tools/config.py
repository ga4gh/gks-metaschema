"""Load and render product-level metaschema configuration.

This module centralizes handling for ``metaschema.yaml`` files, including
version mappings, import paths, namespace templates, and stale schema URL checks.
"""

import os
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

METASCHEMA_FN = "metaschema.yaml"
ALLOWED_CONFIG_KEYS = {"versions", "imports", "namespaces"}
SUPPRESS_UNSUPPORTED_KEY_WARNING_ENV = "GKS_METASCHEMA_SUPPRESS_UNSUPPORTED_KEY_WARNING"
SCHEMA_URL_RE = re.compile(
    r"(?P<prefix>(?:https://w3id\.org/?)?/?ga4gh/schema/(?P<spec>[A-Za-z0-9_.-]+)/)"
    r"(?P<version>[^/\s\"']+)"
    r"(?P<suffix>/)"
)
_WARNED_UNSUPPORTED_CONFIG_KEYS: set[tuple[Path, tuple[str, ...]]] = set()


@dataclass(frozen=True)
class MetaschemaConfig:
    """Validated product-level metaschema configuration.

    :param versions: Mapping of spec names to configured versions.
    :param imports: Mapping of import aliases to source schema paths.
    :param namespaces: Mapping of namespace aliases to URL templates.
    """

    versions: dict[str, str]
    imports: dict[str, str]
    namespaces: dict[str, str]


@dataclass(frozen=True)
class StaleSchemaVersion:
    """A schema URL version that does not match configured versions.

    :param spec: Spec name from the schema URL.
    :param actual_version: Version found in the schema URL.
    :param expected_version: Version configured for the spec.
    """

    spec: str
    actual_version: str
    expected_version: str


def get_expected_metaschema_config_fp(start_fp: Path) -> Path:
    """Get the single metaschema config path expected for a source path.

    Example:
        ``schema/va-spec/base/source.yaml`` resolves to
        ``schema/va-spec/metaschema.yaml``.

    :param start_fp: Source file or directory path to inspect.
    :return: Expected product-level ``metaschema.yaml`` path.
    """
    resolved_start_fp = start_fp.resolve()
    start_dir = resolved_start_fp if resolved_start_fp.is_dir() else resolved_start_fp.parent

    # Product configs live one directory below a directory named "schema".
    # For nested source files, walk upward to that product directory.
    for directory in [start_dir, *start_dir.parents]:
        if directory.parent.name == "schema":
            return directory / METASCHEMA_FN
    return start_dir / METASCHEMA_FN


def load_metaschema_config(config_fp: Path) -> MetaschemaConfig:
    """Load and validate a metaschema project configuration file.

    Example:
        A file containing ``versions: {vrs: 2.0.0}`` returns a config where
        ``config.versions["vrs"] == "2.0.0"`` and omitted allowed sections are
        empty mappings.

    :param config_fp: Path to the metaschema config file.
    :return: Normalized metaschema configuration.
    :raises ValueError: If the config or one of its managed sections is invalid.
    """
    with config_fp.open(encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)

    if config is None:
        return MetaschemaConfig(versions={}, imports={}, namespaces={})

    if not isinstance(config, dict):
        msg = "Metaschema config must be a mapping."
        raise ValueError(msg)

    unknown_keys = set(config) - ALLOWED_CONFIG_KEYS
    if unknown_keys:
        warning_key = (config_fp.resolve(), tuple(sorted(unknown_keys)))
        if (
            not os.environ.get(SUPPRESS_UNSUPPORTED_KEY_WARNING_ENV)
            and warning_key not in _WARNED_UNSUPPORTED_CONFIG_KEYS
        ):
            _WARNED_UNSUPPORTED_CONFIG_KEYS.add(warning_key)
            keys = ", ".join(warning_key[1])
            allowed = ", ".join(sorted(ALLOWED_CONFIG_KEYS))
            warnings.warn(
                f"Ignoring unsupported metaschema config keys: {keys}. Allowed keys are: {allowed}",
                stacklevel=2,
            )

    normalized: dict[str, dict[str, str]] = {}
    for key in ALLOWED_CONFIG_KEYS:
        normalized[key] = _normalize_string_mapping(config.get(key, {}), key)

    return MetaschemaConfig(
        versions=normalized["versions"],
        imports=normalized["imports"],
        namespaces=normalized["namespaces"],
    )


def find_metaschema_config(start_fp: Path) -> Path | None:
    """Find the metaschema config for a source file's product schema directory.

    Example:
        ``schema/va-spec/aac-2017/profile-source.yaml`` uses
        ``schema/va-spec/metaschema.yaml``. A nested
        ``schema/va-spec/aac-2017/metaschema.yaml`` raises an error.

    :param start_fp: Source file or directory path to start from.
    :return: Path to the product-level config, or ``None`` if absent.
    :raises ValueError: If nested ``metaschema.yaml`` files exist below the product directory.
    """
    resolved_start_fp = start_fp.resolve()
    start_dir = resolved_start_fp if resolved_start_fp.is_dir() else resolved_start_fp.parent
    config_fp = get_expected_metaschema_config_fp(start_fp)
    product_dir = config_fp.parent

    # A path outside a product schema directory should not accidentally claim a
    # local metaschema.yaml just because it starts from a directory.
    if product_dir == start_dir and product_dir.parent.name != "schema":
        return None

    if not config_fp.exists():
        return None

    nested_config_fps = [
        directory / METASCHEMA_FN
        for directory in [start_dir, *start_dir.parents]
        if directory != product_dir and product_dir in directory.parents and (directory / METASCHEMA_FN).exists()
    ]

    if nested_config_fps:
        nested_configs = ", ".join(str(nested_config_fp) for nested_config_fp in nested_config_fps)
        msg = f"Nested {METASCHEMA_FN} files are not supported. Use top-level {config_fp} and delete nested config(s): {nested_configs}"
        raise ValueError(msg)

    return config_fp


def load_imported_versions(config_fp: Path, imports: dict[str, str]) -> dict[str, str]:
    """Load versions from imported schema products' product-level metaschema configs.

    Example:
        If ``cat-vrs/metaschema.yaml`` imports ``../vrs/vrs-source.yaml`` and
        VRS defines ``versions: {vrs: 2.2.0}``, this returns ``{"vrs": "2.2.0"}``.

    :param config_fp: Path to the importing metaschema config file.
    :param imports: Mapping of import aliases to source schema paths.
    :return: Version strings from imported products.
    """
    versions: dict[str, str] = {}
    for import_alias, import_value in imports.items():
        import_fp = Path(import_value)

        if not import_fp.is_absolute():
            import_fp = config_fp.parent / import_fp

        # Imported products own their versions. The importing product only names
        # the source it imports.
        imported_config_fp = find_metaschema_config(import_fp)

        if imported_config_fp is None or imported_config_fp == config_fp:
            continue

        imported_versions = load_metaschema_config(imported_config_fp).versions
        versions.update(imported_versions)

        # Some configs use an import alias that differs from the version key.
        # When the imported product has a single version, expose it by alias too.
        if import_alias not in versions and len(imported_versions) == 1:
            versions[import_alias] = next(iter(imported_versions.values()))
    return versions


def _normalize_string_mapping(value: Any, key: str) -> dict[str, str]:
    """Normalize a config section as a string-to-string mapping.

    :param value: Raw YAML value for the config section.
    :param key: Name of the config section being normalized.
    :return: Normalized string mapping.
    :raises ValueError: If the section is not a mapping of strings to strings.
    """
    if value is None:
        return {}

    if not isinstance(value, dict):
        msg = f"Metaschema config '{key}' must be a mapping."
        raise ValueError(msg)

    normalized: dict[str, str] = {}
    for mapping_key, mapping_value in value.items():
        if not isinstance(mapping_key, str) or not isinstance(mapping_value, str):
            msg = f"Metaschema config '{key}' keys and values must be strings."
            raise ValueError(msg)

        normalized[mapping_key] = mapping_value
    return normalized


def render_namespaces(namespaces: dict[str, str], versions: dict[str, str]) -> dict[str, str]:
    """Render namespace templates with configured spec versions.

    Example:
        ``{"vrs": "/ga4gh/schema/vrs/{version}/json/"}`` with
        ``{"vrs": "2.2.0"}`` renders to
        ``{"vrs": "/ga4gh/schema/vrs/2.2.0/json/"}``.

    :param namespaces: Mapping of namespace aliases to URL templates.
    :param versions: Version strings keyed by spec or alias.
    :return: Namespace values with placeholders rendered.
    :raises ValueError: If ``{version}`` cannot be resolved, or if a concrete
        namespace URL version does not match the configured version.
    """
    rendered: dict[str, str] = {}
    for key, value in namespaces.items():
        spec = _get_schema_url_spec(value) or key
        version = versions.get(key, versions.get(spec))
        if "{version}" in value and version is None:
            msg = f"namespace {key} uses {{version}} but no version is configured for {spec}"
            raise ValueError(msg)

        rendered_value = value.format(spec=spec, version=version or "")

        stale_versions = find_stale_schema_url_versions(rendered_value, versions)
        if stale_versions:
            messages = [
                f"namespace {key} {version.spec} version is {version.actual_version}; "
                f"expected {version.expected_version}"
                for version in stale_versions
            ]
            raise ValueError("; ".join(messages))

        rendered[key] = render_schema_url_versions(rendered_value, versions)
    return rendered


def _get_schema_url_spec(text: str) -> str | None:
    """Get the spec name from the first GA4GH schema URL in text.

    :param text: Text that may contain a GA4GH schema URL.
    :return: Spec name from the first schema URL, or ``None`` if absent.
    """
    match = SCHEMA_URL_RE.search(text)
    if match is None:
        return None
    return match.group("spec")


def render_schema_url_versions(text: str, versions: dict[str, str]) -> str:
    """Render configured GA4GH schema URL version segments.

    Example:
        ``/ga4gh/schema/vrs/{version}/json/`` becomes
        ``/ga4gh/schema/vrs/2.2.0/json/`` when ``versions["vrs"] == "2.2.0"``.

    :param text: Text that may contain GA4GH schema URLs.
    :param versions: Version strings keyed by spec name.
    :return: Text with matching schema URL version segments rendered.
    """

    def replace(match: re.Match[str]) -> str:
        """Replace one configured schema URL version segment.

        :param match: Regex match for a GA4GH schema URL.
        :return: Original or rendered URL text.
        """
        spec = match.group("spec")
        version = versions.get(spec)

        if version is None:
            return match.group(0)

        return f"{match.group('prefix')}{version}{match.group('suffix')}"

    return SCHEMA_URL_RE.sub(replace, text)


def find_stale_schema_url_versions(text: str, versions: dict[str, str]) -> list[StaleSchemaVersion]:
    """Find GA4GH schema URL versions that do not match configured versions.

    Example:
        ``/ga4gh/schema/vrs/2.0.0/json/`` with ``{"vrs": "2.2.0"}``
        returns a stale version record for VRS.

    :param text: Text that may contain GA4GH schema URLs.
    :param versions: Version strings keyed by spec name.
    :return: Stale schema version records.
    """
    stale_versions: list[StaleSchemaVersion] = []
    for match in SCHEMA_URL_RE.finditer(text):
        spec = match.group("spec")
        expected_version = versions.get(spec)
        actual_version = match.group("version")

        if expected_version is not None and actual_version != expected_version:
            stale_versions.append(StaleSchemaVersion(spec, actual_version, expected_version))
    return stale_versions
