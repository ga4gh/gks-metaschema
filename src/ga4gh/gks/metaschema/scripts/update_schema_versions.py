"""Update or check source YAML files against metaschema-configured versions.

The CLI rewrites managed GA4GH schema URL versions, removes source-local config
sections, and can fail on stale or hard-coded versioned references.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from ga4gh.gks.metaschema.tools.config import (
    ALLOWED_CONFIG_KEYS,
    METASCHEMA_FN,
    SCHEMA_URL_RE,
    find_metaschema_config,
    get_expected_metaschema_config_fp,
    load_imported_versions,
    load_metaschema_config,
)


@dataclass(frozen=True)
class VersionReference:
    """A GA4GH schema URL whose version differs from the configured version."""

    file: Path
    line: int
    spec: str
    actual_version: str
    expected_version: str


@dataclass(frozen=True)
class HardcodedReference:
    """A hard-coded versioned ``$ref`` URL for a configured spec."""

    file: Path
    line: int
    spec: str
    ref: str


@dataclass(frozen=True)
class SourceLocalConfigKey:
    """A source-local key that is managed by metaschema config."""

    file: Path
    key: str


@dataclass(frozen=True)
class SourceUpdateConfig:
    """Resolved config values used to update source YAML files.

    :param versions: Mapping of spec names or import aliases to configured versions.
    :param managed_keys: Source-local top-level keys managed by ``metaschema.yaml``.
    """

    versions: dict[str, str]
    managed_keys: set[str]


def _load_versions(config_fp: Path) -> dict[str, str]:
    """Load configured spec versions from a metaschema config file.

    Example:
        A product config with local versions and imports returns one mapping
        containing both local and imported product versions.

    :param config_fp: Path to the metaschema config file.
    :return: Mapping of spec names or import aliases to configured versions.
    """
    config = load_metaschema_config(config_fp)
    return load_imported_versions(config_fp, config.imports) | config.versions


def _load_managed_keys(config_fp: Path) -> set[str]:
    """Load config keys that should not be duplicated in source YAML.

    Example:
        A config containing ``versions`` and ``namespaces`` returns
        ``{"versions", "namespaces"}``.

    :param config_fp: Path to the metaschema config file.
    :return: Managed top-level source keys found in the config.
    """
    with config_fp.open(encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)

    if not isinstance(config, dict):
        return set()

    return set(config) & ALLOWED_CONFIG_KEYS


def _iter_source_files(paths: list[Path]) -> list[Path]:
    """Return source YAML files from a mix of files and directories.

    Example:
        ``[Path("schema/va-spec")]`` returns source files such as
        ``schema/va-spec/base/va-core-source.yaml`` and
        ``schema/va-spec/aac-2017/profile-source.yaml``.

    :param paths: Source files or directories to scan.
    :return: Sorted unique list of source YAML files.
    """
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*-source.yaml")))
        else:
            files.append(path)
    return sorted(set(files))


def _find_config_for_file(file: Path) -> Path:
    """Find the metaschema config for a source YAML file.

    Example:
        ``schema/cat-vrs/profiles/source.yaml`` resolves to
        ``schema/cat-vrs/metaschema.yaml``.

    :param file: Source YAML file.
    :return: Product metaschema config path.
    :raises ValueError: If no config exists for the source file.
    """
    config_fp = find_metaschema_config(file)
    if config_fp is not None:
        return config_fp

    resolved_file = file.resolve()
    expected_config_fp = get_expected_metaschema_config_fp(resolved_file)
    msg = f"No {METASCHEMA_FN} config found for {resolved_file}. Expected product config at {expected_config_fp}"
    raise ValueError(msg)


def update_schema_url_versions_in_text(text: str, versions: dict[str, str]) -> tuple[str, list[VersionReference]]:
    """Return text with configured GA4GH schema versions updated.

    Only URL/path segments matching ``/ga4gh/schema/{spec}/{version}/`` are
    changed. This covers w3id ``$id`` values, namespace URLs, and hard-coded
    ``$ref`` values while preserving the rest of the YAML source formatting.

    Example:
        ``/ga4gh/schema/vrs/2.0.0/json/`` with ``{"vrs": "2.2.0"}``
        becomes ``/ga4gh/schema/vrs/2.2.0/json/``.

    :param text: Source YAML text to update.
    :param versions: Mapping of spec names to target versions.
    :return: Updated source text and references that were changed. The returned
        references have empty ``file`` and line ``0`` because this helper only
        receives text.
    """
    references: list[VersionReference] = []

    def replace(match: re.Match[str]) -> str:
        """Replace one configured schema URL version match.

        :param match: Regex match for a GA4GH schema URL.
        :return: Original or updated URL text.
        """
        spec = match.group("spec")
        actual_version = match.group("version")
        expected_version = versions.get(spec)

        if expected_version is None or actual_version == expected_version:
            return match.group(0)

        references.append(
            VersionReference(
                file=Path(),
                line=0,
                spec=spec,
                actual_version=actual_version,
                expected_version=expected_version,
            )
        )
        return f"{match.group('prefix')}{expected_version}{match.group('suffix')}"

    return SCHEMA_URL_RE.sub(replace, text), references


def remove_managed_source_keys(text: str, managed_keys: set[str]) -> tuple[str, list[str]]:
    """Remove source-local top-level keys that are managed by metaschema config.

    Example:
        If ``managed_keys`` contains ``"namespaces"``, a top-level
        ``namespaces:`` block is removed from the source text.

    :param text: Source YAML text to clean.
    :param managed_keys: Top-level config keys present in ``metaschema.yaml``.
    :return: Cleaned text and removed key names.
    """
    if not managed_keys:
        return text, []

    lines = text.splitlines(keepends=True)
    cleaned_lines: list[str] = []
    removed_keys: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(?P<key>[A-Za-z][A-Za-z0-9_.-]*):(?:\s.*)?$", line)

        if match is None or match.group("key") not in managed_keys:
            cleaned_lines.append(line)
            index += 1
            continue

        # Drop the matched top-level block, including indented children and
        # blank separator lines that belong to that block.
        removed_keys.append(match.group("key"))
        index += 1
        while index < len(lines):
            next_line = lines[index]

            if next_line.strip() == "" or next_line.startswith((" ", "\t")):
                index += 1
                continue

            break

    return "".join(cleaned_lines), removed_keys


def find_stale_version_references(file: Path, text: str, versions: dict[str, str]) -> list[VersionReference]:
    """Find configured schema URLs whose versions do not match config.

    Example:
        A line containing ``/ga4gh/schema/vrs/2.0.0/json/`` is reported when
        ``versions["vrs"] == "2.2.0"``.

    :param file: File path used in reported references.
    :param text: Source YAML text to inspect.
    :param versions: Mapping of spec names to target versions.
    :return: Stale version references found in the text.
    """
    references: list[VersionReference] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in SCHEMA_URL_RE.finditer(line):
            spec = match.group("spec")
            actual_version = match.group("version")
            expected_version = versions.get(spec)

            if expected_version is not None and actual_version != expected_version:
                references.append(VersionReference(file, line_no, spec, actual_version, expected_version))
    return references


def find_hardcoded_versioned_refs(file: Path, text: str, versions: dict[str, str]) -> list[HardcodedReference]:
    """Find hard-coded versioned ``$ref`` URLs for configured specs.

    Example:
        ``$ref: /ga4gh/schema/vrs/2.2.0/json/Allele`` is reported when
        ``vrs`` is configured, because source files should use ``$refCurie``.

    :param file: File path used in reported references.
    :param text: Source YAML text to inspect.
    :param versions: Mapping of spec names to target versions.
    :return: Hard-coded versioned ``$ref`` references found in the text.
    """
    references: list[HardcodedReference] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        uncommented_line = line.split("#", 1)[0]
        if "$ref" not in uncommented_line:
            continue

        for match in SCHEMA_URL_RE.finditer(uncommented_line):
            spec = match.group("spec")

            if spec in versions:
                references.append(HardcodedReference(file, line_no, spec, match.group(0)))
    return references


def update_source_file(
    file: Path,
    versions: dict[str, str],
    managed_keys: set[str],
    check: bool = False,
) -> tuple[list[VersionReference], list[SourceLocalConfigKey]]:
    """Update one source YAML file or report stale references.

    Example:
        With ``check=False``, a file containing a stale VRS URL is rewritten in
        place. With ``check=True``, the stale reference is returned but the file
        is not edited.

    :param file: Source YAML file to update or check.
    :param versions: Mapping of spec names to target versions.
    :param managed_keys: Top-level config keys present in ``metaschema.yaml``.
    :param check: Whether to report without editing. ``True`` performs a dry run.
    :return: Stale references and source-local config keys found before any edit.
    """
    text = file.read_text(encoding="utf-8")
    stale_references = find_stale_version_references(file, text, versions)
    cleaned_text, removed_keys = remove_managed_source_keys(text, managed_keys)
    source_local_keys = [SourceLocalConfigKey(file, key) for key in removed_keys]

    if check:
        return stale_references, source_local_keys

    updated_text, _ = update_schema_url_versions_in_text(cleaned_text, versions)
    file.write_text(updated_text, encoding="utf-8")
    return stale_references, source_local_keys


def _format_reference(reference: VersionReference) -> str:
    """Format a stale schema version reference for CLI output.

    :param reference: Stale schema version reference.
    :return: Human-readable reference message.
    """
    location = f"{reference.file}:{reference.line}" if reference.line else str(reference.file)
    return f"{location}: {reference.spec} is {reference.actual_version}; expected {reference.expected_version}"


def _format_hardcoded_reference(reference: HardcodedReference) -> str:
    """Format a hard-coded ``$ref`` reference for CLI output.

    :param reference: Hard-coded reference.
    :return: Human-readable reference message.
    """
    return f"{reference.file}:{reference.line}: {reference.spec} hard-coded $ref {reference.ref}"


def _format_source_local_key(source_local_key: SourceLocalConfigKey) -> str:
    """Format a source-local config key for CLI output.

    :param source_local_key: Source-local config key.
    :return: Human-readable cleanup message.
    """
    return f"{source_local_key.file}: {source_local_key.key} is managed by {METASCHEMA_FN}"


def main(argv: list[str] | None = None) -> int:
    """Run the update/check command.

    Expects a YAML file (located at ``metaschema.yaml``) that contains versions,
    imports, and namespace mappings.

    :param argv: Optional CLI arguments. Uses ``sys.argv`` when omitted.
    :return: Process exit code, ``0`` for success and ``1`` when check failures
        or hard-coded refs are found.
    """
    parser = argparse.ArgumentParser(
        description="Update or check GA4GH schema version URL segments in *-source.yaml files."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Source YAML files or directories to scan.")
    parser.add_argument("--check", action="store_true", help="Report stale references without editing files.")
    parser.add_argument(
        "--disallow-versioned-refs",
        action="store_true",
        help="Fail if configured specs are referenced through hard-coded versioned $ref URLs.",
    )
    args = parser.parse_args(argv)

    files = _iter_source_files(args.paths)

    stale_references: list[VersionReference] = []
    hardcoded_references: list[HardcodedReference] = []
    source_local_keys: list[SourceLocalConfigKey] = []
    config_cache: dict[Path, SourceUpdateConfig] = {}

    for file in files:
        config_fp = _find_config_for_file(file)

        if config_fp not in config_cache:
            config_cache[config_fp] = SourceUpdateConfig(
                versions=_load_versions(config_fp),
                managed_keys=_load_managed_keys(config_fp),
            )

        config = config_cache[config_fp]
        file_stale_references, file_source_local_keys = update_source_file(
            file,
            config.versions,
            config.managed_keys,
            check=args.check,
        )
        stale_references.extend(file_stale_references)
        source_local_keys.extend(file_source_local_keys)

        if args.disallow_versioned_refs:
            hardcoded_references.extend(
                find_hardcoded_versioned_refs(file, file.read_text(encoding="utf-8"), config.versions)
            )

    if args.check and stale_references:
        print("Stale GA4GH schema version references found:", file=sys.stderr)

        for reference in stale_references:
            print(f"  {_format_reference(reference)}", file=sys.stderr)

    if hardcoded_references:
        print("Hard-coded versioned $ref references found:", file=sys.stderr)

        for reference in hardcoded_references:
            print(f"  {_format_hardcoded_reference(reference)}", file=sys.stderr)

    if args.check and source_local_keys:
        print(f"Source-local keys managed by {METASCHEMA_FN} found:", file=sys.stderr)

        for source_local_key in source_local_keys:
            print(f"  {_format_source_local_key(source_local_key)}", file=sys.stderr)

    if (args.check and (stale_references or source_local_keys)) or hardcoded_references:
        return 1

    for source_local_key in source_local_keys:
        print(f"removed {_format_source_local_key(source_local_key)}")

    if stale_references:
        changed_files = sorted({str(reference.file) for reference in stale_references})
        for file in changed_files:
            print(f"updated {file}")

    return 0


def cli() -> None:
    """Console script entry point."""
    raise SystemExit(main())


if __name__ == "__main__":
    cli()
