"""Product schema paths and ``metaschema.yaml`` version updates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ga4gh.gks.metaschema.tools.config import METASCHEMA_FN

SCHEMA_DIR_NAME = "schema"
VERSIONS_KEY = "versions"


def infer_product_from_repo_dir(repo_dir: Path) -> str:
    """Infer the product name from its repository directory.

    Example:
        A repository root ending in ``va-spec`` returns ``"va-spec"``.

    :param repo_dir: Product repository root directory.
    :return: Product directory and version key.
    :raises ValueError: If the resolved directory has no name.
    """
    product = repo_dir.resolve().name
    if product:
        return product

    msg = f"Could not infer product name from repository root: {repo_dir}"
    raise ValueError(msg)


def resolve_product_dir(repo_dir: Path, product: str) -> Path:
    """Return the product schema directory containing ``metaschema.yaml``.

    Example:
        ``Path(".")`` and ``"va-spec"`` resolve to ``schema/va-spec``.

    :param repo_dir: Product repository root directory.
    :param product: Product directory and version key.
    :return: Resolved product schema directory.
    :raises ValueError: If the product config cannot be found.
    """
    candidate = repo_dir / SCHEMA_DIR_NAME / product
    if (candidate / METASCHEMA_FN).exists():
        return candidate.resolve()

    msg = f"No {METASCHEMA_FN} found for product {product}. Checked: {candidate}"
    raise ValueError(msg)


def get_schema_build_dir(product_dir: Path) -> Path:
    """Return the directory where product ``make all`` should run.

    :param product_dir: Product schema directory.
    :return: Parent ``schema`` directory, or ``product_dir`` when it is not
        nested below a directory named ``schema``.
    """
    if product_dir.parent.name == SCHEMA_DIR_NAME:
        return product_dir.parent
    return product_dir


def update_product_version(config_fp: Path, product: str, version: str) -> None:
    """Set the local product version in a ``metaschema.yaml`` mapping.

    This writes ``config_fp`` in place while preserving top-level key order.

    :param config_fp: Path to ``metaschema.yaml``.
    :param product: Local product version key.
    :param version: Version to write.
    :raises ValueError: If the config or its ``versions`` key is not a mapping.
    """
    config = _load_config_document(config_fp)
    versions = config.setdefault(VERSIONS_KEY, {})
    if not isinstance(versions, dict):
        msg = f"{config_fp} versions must be a mapping."
        raise ValueError(msg)

    versions[product] = version
    with config_fp.open("w", encoding="utf-8") as stream:
        yaml.dump(config, stream, sort_keys=False)


def _load_config_document(config_fp: Path) -> dict[str, Any]:
    """Load a mutable YAML mapping from a product config file.

    :param config_fp: Path to ``metaschema.yaml``.
    :return: Parsed config mapping, or an empty mapping for an empty file.
    :raises ValueError: If the config content is not a mapping.
    """
    with config_fp.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    if config is None:
        return {}
    if isinstance(config, dict):
        return config

    msg = f"{config_fp} must contain a YAML mapping."
    raise ValueError(msg)
