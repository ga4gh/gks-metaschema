"""Tests for release-prep product configuration updates."""

from pathlib import Path

from ga4gh.gks.metaschema.tools.release_prep.product_config import (
    update_product_version,
)


def test_update_product_version_replaces_config_without_leaving_temp_files(
    tmp_path: Path,
) -> None:
    """Write an updated config and remove the temporary write file."""
    config_fp = tmp_path / "metaschema.yaml"
    config_fp.write_text("versions:\n  example: 1.0.0\n", encoding="utf-8")

    update_product_version(config_fp, "example", "1.1.0")

    assert config_fp.read_text(encoding="utf-8") == "versions:\n  example: 1.1.0\n"
    assert not list(tmp_path.glob(".metaschema.yaml.*"))
