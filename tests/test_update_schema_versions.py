"""Tests for updating source YAML files from metaschema configuration."""

import re
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from ga4gh.gks.metaschema.tools.release_prep.schema_versions import (
    main as update_schema_versions,
)


def test_update_schema_versions_updates_configured_refs(
    schema_case_root: Path, tmp_path: Path
) -> None:
    shutil.copytree(schema_case_root / "update", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/profile-source.yaml"

    assert update_schema_versions([str(source)]) == 0

    updated = source.read_text()
    assert (
        "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/va-spec-source.yaml"
        in updated
    )
    assert (
        '"/ga4gh/schema/va-spec/1.1.0/base/json/VariantPrognosticProposition"'
        in updated
    )
    assert '"/ga4gh/schema/unmanaged/9.9.9/json/Thing"' in updated
    assert "namespaces:" not in updated


def test_update_schema_versions_discovers_config_from_path(
    schema_case_root: Path, tmp_path: Path
) -> None:
    shutil.copytree(schema_case_root / "update", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/profile-source.yaml"

    assert update_schema_versions([str(tmp_path / "schema")]) == 0

    assert (
        "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/va-spec-source.yaml"
        in source.read_text()
    )


def test_update_schema_versions_uses_product_config_under_schema_root(
    schema_case_root: Path, tmp_path: Path
) -> None:
    shutil.copytree(schema_case_root / "schema-root", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/va-spec/base/domain-entities-source.yaml"

    assert update_schema_versions([str(tmp_path / "schema")]) == 0

    assert (
        "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/domain-entities-source.yaml"
        in source.read_text()
    )


def test_update_schema_versions_check_reports_source_local_config_keys(
    schema_case_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copytree(schema_case_root / "source-local", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/example-source.yaml"

    assert update_schema_versions(["--check", str(source)]) == 1

    stderr = capsys.readouterr().err
    assert "imports is managed by metaschema.yaml" in stderr
    assert "namespaces is managed by metaschema.yaml" in stderr


def test_update_schema_versions_noops_without_default_config(
    schema_case_root: Path, tmp_path: Path
) -> None:
    shutil.copytree(schema_case_root / "no-config", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/example-source.yaml"

    with pytest.raises(
        ValueError, match=re.escape("No metaschema.yaml config found for")
    ):
        update_schema_versions([str(source)])


def test_update_schema_versions_check_reports_stale_refs(
    schema_case_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copytree(schema_case_root / "check", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/example-source.yaml"

    assert update_schema_versions(["--check", str(source)]) == 1

    assert "va-spec is 1.0.1; expected 1.1.0" in capsys.readouterr().err
    assert "1.0.1" in source.read_text()


def test_update_schema_versions_check_rejects_version_template(
    schema_case_fixture: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    source = schema_case_fixture("check") / "current-template-source.yaml"

    assert update_schema_versions(["--check", str(source)]) == 1

    assert "va-spec is {version}; expected 1.1.0" in capsys.readouterr().err


def test_update_schema_versions_can_disallow_hardcoded_refs(
    schema_case_fixture: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    source = schema_case_fixture("update") / "profile-source.yaml"
    assert update_schema_versions(["--disallow-versioned-refs", str(source)]) == 1
    assert "hard-coded $ref" in capsys.readouterr().err


def test_update_schema_versions_ignores_commented_hardcoded_refs(
    schema_case_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copytree(schema_case_root / "update", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/profile-source.yaml"
    source.write_text(
        '\n$id: "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/profile-source.yaml"\n'
        "$defs:\n"
        "  Example:\n"
        '    # $ref: "/ga4gh/schema/va-spec/1.1.0/base/json/CommentedOutProposition"\n',
        encoding="utf-8",
    )

    assert update_schema_versions(["--disallow-versioned-refs", str(source)]) == 0
    assert "hard-coded $ref" not in capsys.readouterr().err
