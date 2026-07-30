"""Prepare a GKS product schema release from metaschema configuration.

The release-prep command orchestrates the repeatable release steps that product
maintainers otherwise run manually: update the immediate upstream submodule
branch, check out the selected upstream tag, set the local product version,
regenerate artifacts, and verify source YAML version references.
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ga4gh.gks.metaschema.scripts.release_prep_git import (
    CommandOutputRunner,
    CommandRunner,
    Reporter,
    SubmoduleUpdate,
)
from ga4gh.gks.metaschema.scripts.release_prep_git import (
    get_product_repo_dir as _get_product_repo_dir,
)
from ga4gh.gks.metaschema.scripts.release_prep_git import (
    infer_submodule_update as _infer_submodule_update,
)
from ga4gh.gks.metaschema.scripts.release_prep_git import (
    infer_submodule_update_from_current_branch as _infer_submodule_update_from_current_branch,
)
from ga4gh.gks.metaschema.scripts.release_prep_git import (
    require_clean_worktree as _require_clean_worktree,
)
from ga4gh.gks.metaschema.scripts.release_prep_git import (
    require_upstream_branch_when_submodule_exists as _require_upstream_branch_when_submodule_exists,
)
from ga4gh.gks.metaschema.scripts.release_prep_git import (
    update_submodule as _update_submodule,
)
from ga4gh.gks.metaschema.scripts.release_prep_git import (
    validate_submodule as _validate_submodule,
)
from ga4gh.gks.metaschema.scripts.release_prep_git import (
    warn_if_product_branch_not_current as _warn_if_product_branch_not_current,
)
from ga4gh.gks.metaschema.scripts.release_prep_git import (
    warn_if_worktree_dirty as _warn_if_worktree_dirty,
)
from ga4gh.gks.metaschema.scripts.update_schema_versions import main as update_schema_versions
from ga4gh.gks.metaschema.tools.config import (
    METASCHEMA_FN,
    SUPPRESS_UNSUPPORTED_KEY_WARNING_ENV,
    load_metaschema_config,
)

SCHEMA_DIR_NAME = "schema"
VERSIONS_KEY = "versions"
SOURCE_UPDATE_CHECK_FLAG = "--check"
SOURCE_UPDATE_DISALLOW_VERSIONED_REFS_FLAG = "--disallow-versioned-refs"
SOURCE_UPDATE_COMMAND_NAME = "source2updated"
MAKE_ALL_COMMAND = ("make", "all")


def _run_command(command: list[str], cwd: Path) -> None:
    """Run a command for release prep.

    :param command: Command and arguments to run.
    :param cwd: Working directory for the command.
    :raises subprocess.CalledProcessError: If the command exits with a
        non-zero status.
    """
    subprocess.run(command, cwd=cwd, check=True)


def _run_command_output(command: list[str], cwd: Path) -> str:
    """Run a command and return standard output.

    :param command: Command and arguments to run.
    :param cwd: Working directory for the command.
    :return: Command standard output with surrounding whitespace removed.
    :raises subprocess.CalledProcessError: If the command exits with a
        non-zero status.
    """
    completed = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


@dataclass(frozen=True)
class ReleasePrepSummary:
    """Summary of release-prep actions.

    :param product: Product version key updated in ``metaschema.yaml``.
    :param version: Product version written to ``metaschema.yaml``.
    :param product_dir: Product schema directory.
    :param submodules: Immediate upstream submodule update that was requested.
    :param validated_only: Whether the command only validated inputs.
    """

    product: str
    version: str
    product_dir: Path
    submodules: list[SubmoduleUpdate]
    validated_only: bool = False


def _resolve_product_dir(repo_dir: Path, product: str) -> Path:
    """Resolve the product schema directory.

    Example:
        ``.`` and ``va-spec`` resolves to ``schema/va-spec``.

    :param repo_dir: Product repository root directory.
    :param product: Product directory/version key.
    :return: Product schema directory.
    :raises ValueError: If the product config cannot be found.
    """
    candidate = repo_dir / SCHEMA_DIR_NAME / product

    if (candidate / METASCHEMA_FN).exists():
        return candidate.resolve()

    msg = f"No {METASCHEMA_FN} found for product {product}. Checked: {candidate}"
    raise ValueError(msg)


def _infer_product_from_repo_dir(repo_dir: Path) -> str:
    """Infer the product name from the product repository root directory.

    Example:
        A repository root path ending in ``va-spec`` returns ``va-spec``.

    :param repo_dir: Product repository root directory.
    :return: Product directory/version key inferred from the repository name.
    :raises ValueError: If the repository root name is empty.
    """
    product = repo_dir.resolve().name

    if product:
        return product

    msg = f"Could not infer product name from repository root: {repo_dir}"
    raise ValueError(msg)


def _get_schema_build_dir(product_dir: Path) -> Path:
    """Get the directory where ``make all`` should run.

    :param product_dir: Product schema directory.
    :return: Parent schema directory when the product lives under ``schema``;
        otherwise the product directory itself.
    """
    if product_dir.parent.name == SCHEMA_DIR_NAME:
        return product_dir.parent

    return product_dir


def _report(reporter: Reporter | None, message: str) -> None:
    """Report release-prep progress when a reporter is configured.

    :param reporter: Optional progress reporter, such as ``print``.
    :param message: Message to report.
    """
    if reporter is not None:
        reporter(message)


def _load_config_document(config_fp: Path) -> dict[str, Any]:
    """Load raw metaschema config YAML as a mutable mapping.

    Release prep loads raw YAML instead of ``MetaschemaConfig`` because it needs
    to write the original config document back after changing only ``versions``.

    :param config_fp: Path to ``metaschema.yaml``.
    :return: Mutable config mapping.
    :raises ValueError: If the config is not a mapping.
    """
    with config_fp.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    if config is None:
        return {}

    if not isinstance(config, dict):
        msg = f"{config_fp} must contain a YAML mapping."
        raise ValueError(msg)

    return config


def _write_config_document(config_fp: Path, config: dict[str, Any]) -> None:
    """Write a metaschema config mapping.

    :param config_fp: Path to ``metaschema.yaml``.
    :param config: Config mapping to write.
    """
    with config_fp.open("w", encoding="utf-8") as stream:
        yaml.dump(config, stream, sort_keys=False)


def _update_product_version(config_fp: Path, product: str, version: str) -> None:
    """Set the local product version in ``metaschema.yaml``.

    :param config_fp: Path to ``metaschema.yaml``.
    :param product: Product version key to update.
    :param version: Version to write.
    :raises ValueError: If the existing ``versions`` section is not a mapping.
    """
    config = _load_config_document(config_fp)
    versions = config.setdefault(VERSIONS_KEY, {})

    if not isinstance(versions, dict):
        msg = f"{config_fp} versions must be a mapping."
        raise ValueError(msg)

    versions[product] = version
    _write_config_document(config_fp, config)


def _run_source_update(product_dir: Path, check: bool) -> int:
    """Run source version management for a product directory.

    :param product_dir: Product schema directory.
    :param check: Whether to run in check mode.
    :return: Exit code from ``source2updated``.
    """
    argv = [SOURCE_UPDATE_DISALLOW_VERSIONED_REFS_FLAG, str(product_dir)]

    if check:
        argv.insert(0, SOURCE_UPDATE_CHECK_FLAG)

    return update_schema_versions(argv)


def _suppress_repeated_config_warnings() -> str | None:
    """Suppress config warning repeats and return the previous env value.

    :return: Previous suppression env value, or ``None`` when unset.
    """
    previous = os.environ.get(SUPPRESS_UNSUPPORTED_KEY_WARNING_ENV)
    os.environ[SUPPRESS_UNSUPPORTED_KEY_WARNING_ENV] = "1"
    return previous


def _restore_repeated_config_warnings(previous: str | None) -> None:
    """Restore the repeated config warning suppression env var.

    :param previous: Previous env value returned by
        ``_suppress_repeated_config_warnings``.
    """
    if previous is None:
        os.environ.pop(SUPPRESS_UNSUPPORTED_KEY_WARNING_ENV, None)
        return

    os.environ[SUPPRESS_UNSUPPORTED_KEY_WARNING_ENV] = previous


def _source_update_label(check: bool) -> str:
    """Build the user-facing source update command label.

    :param check: Whether to include check mode in the command label.
    :return: Source update command label.
    """
    flags = [SOURCE_UPDATE_DISALLOW_VERSIONED_REFS_FLAG]

    if check:
        flags.insert(0, SOURCE_UPDATE_CHECK_FLAG)

    return " ".join([SOURCE_UPDATE_COMMAND_NAME, *flags])


def _validate_submodule_count(submodules: list[SubmoduleUpdate]) -> None:
    """Validate release prep only targets the immediate upstream submodule.

    :param submodules: Requested submodule updates.
    :raises ValueError: If more than one submodule update is requested.
    """
    if len(submodules) > 1:
        msg = (
            "Release prep supports one immediate upstream submodule update. "
            "Update transitive upstream products in their own release branches first."
        )
        raise ValueError(msg)


def _warn_if_downstream_branch_not_current(
    product_dir: Path,
    submodules: list[SubmoduleUpdate],
    output_runner: CommandOutputRunner,
    reporter: Reporter | None,
) -> None:
    """Warn about product branch freshness for downstream releases.

    First-chain products such as ``gks-core`` have no upstream submodule, so a
    missing upstream tracking branch is usually local workflow noise instead of
    release-prep signal.

    :param product_dir: Product schema directory.
    :param submodules: Requested immediate upstream submodule updates.
    :param output_runner: Command runner for git commands that return output.
    :param reporter: Optional progress reporter.
    """
    if not submodules:
        return

    _warn_if_product_branch_not_current(_get_product_repo_dir(product_dir), output_runner, reporter)


def _handle_dirty_worktree(
    repo_dir: Path,
    label: str,
    output_runner: CommandOutputRunner,
    reporter: Reporter | None,
    fail_on_dirty: bool,
) -> None:
    """Warn or fail when a git working tree has uncommitted changes.

    :param repo_dir: Git repository directory to inspect.
    :param label: Human-readable repository label.
    :param output_runner: Command runner for git commands that return output.
    :param reporter: Optional progress reporter.
    :param fail_on_dirty: Whether dirty worktrees should fail release prep.
    :raises ValueError: If ``fail_on_dirty`` is true and the worktree has
        uncommitted changes.
    """
    if fail_on_dirty:
        _require_clean_worktree(repo_dir, label, output_runner)
        return

    _warn_if_worktree_dirty(repo_dir, label, output_runner, reporter)


def validate_release(
    product: str,
    version: str,
    repo_dir: Path = Path("."),
    submodules: list[SubmoduleUpdate] | None = None,
    runner: CommandRunner = _run_command,
    output_runner: CommandOutputRunner = _run_command_output,
    reporter: Reporter | None = None,
    fail_on_dirty: bool = False,
) -> ReleasePrepSummary:
    """Validate release-prep inputs without mutating the working tree.

    :param product: Product directory/version key.
    :param version: Product version to validate.
    :param repo_dir: Product repository root directory.
    :param submodules: Optional immediate upstream submodule update in
        submodule/branch form. More than one update is rejected.
    :param runner: Command runner for git validation commands.
    :param output_runner: Command runner for git commands that return output.
    :param reporter: Optional progress reporter. When set, validation messages
        are sent to this callable.
    :param fail_on_dirty: Whether dirty product or submodule worktrees should
        fail validation instead of printing warnings.
    :return: Validation summary with resolved submodule tag.
    :raises ValueError: If multiple submodule updates are requested, config
        paths are invalid, or submodule validation fails.
    """
    requested_submodules = submodules or []
    _validate_submodule_count(requested_submodules)
    _report(reporter, f"Validating release for product {product} version {version}")
    product_dir = _resolve_product_dir(repo_dir, product)
    _report(reporter, f"Using product schema: {product_dir}")
    _handle_dirty_worktree(
        _get_product_repo_dir(product_dir),
        f"Product {product}",
        output_runner,
        reporter,
        fail_on_dirty,
    )
    _warn_if_downstream_branch_not_current(product_dir, requested_submodules, output_runner, reporter)
    load_metaschema_config(product_dir / METASCHEMA_FN)
    resolved_submodules: list[SubmoduleUpdate] = []

    for submodule in requested_submodules:
        _report(reporter, f"Validating submodule {submodule.identifier} on branch {submodule.branch}")
        _submodule_dir, _entry, resolved_submodule = _validate_submodule(
            submodule,
            product_dir,
            runner,
            output_runner,
            reporter=reporter,
            fail_on_dirty=fail_on_dirty,
        )
        _report(reporter, f"Resolved submodule {submodule.identifier} tag {resolved_submodule.tag}")
        resolved_submodules.append(resolved_submodule)

    return ReleasePrepSummary(
        product=product,
        version=version,
        product_dir=product_dir,
        submodules=resolved_submodules,
        validated_only=True,
    )


def prepare_release(
    product: str,
    version: str,
    repo_dir: Path = Path("."),
    submodules: list[SubmoduleUpdate] | None = None,
    runner: CommandRunner = _run_command,
    output_runner: CommandOutputRunner = _run_command_output,
    reporter: Reporter | None = None,
    fail_on_dirty: bool = False,
) -> ReleasePrepSummary:
    """Prepare source and generated files for a product release.

    The function mutates the product ``metaschema.yaml`` by setting the local
    product version, may update the immediate upstream git submodule, updates
    source YAML version references before build validation runs, runs
    ``make all`` to regenerate artifacts, then verifies the source YAML files
    are release-ready.

    :param product: Product directory/version key.
    :param version: Product version to write.
    :param repo_dir: Product repository root directory.
    :param submodules: Optional immediate upstream submodule update in
        submodule/branch form. More than one update is rejected.
    :param runner: Command runner for git and make commands.
    :param output_runner: Command runner for git commands that return output.
    :param reporter: Optional progress reporter. When set, release-prep
        messages are sent to this callable.
    :param fail_on_dirty: Whether dirty product or submodule worktrees should
        fail release prep instead of printing warnings.
    :return: Release-prep summary.
    :raises ValueError: If multiple submodule updates are requested, config
        paths are invalid, or source checks fail.
    :raises subprocess.CalledProcessError: If a git or make command fails.
    """
    requested_submodules = submodules or []
    _validate_submodule_count(requested_submodules)

    _report(reporter, f"Preparing release for product {product} version {version}")
    product_dir = _resolve_product_dir(repo_dir, product)
    _report(reporter, f"Using product schema: {product_dir}")
    _handle_dirty_worktree(
        _get_product_repo_dir(product_dir),
        f"Product {product}",
        output_runner,
        reporter,
        fail_on_dirty,
    )
    _warn_if_downstream_branch_not_current(product_dir, requested_submodules, output_runner, reporter)
    config_fp = product_dir / METASCHEMA_FN
    resolved_submodules: list[SubmoduleUpdate] = []

    for submodule in requested_submodules:
        _report(reporter, f"Updating submodule {submodule.identifier} on branch {submodule.branch}")
        resolved_submodules.append(
            _update_submodule(
                submodule,
                product_dir,
                runner,
                output_runner,
                reporter=reporter,
                fail_on_dirty=fail_on_dirty,
            )
        )
        _report(reporter, f"Checked out submodule {submodule.identifier} tag {resolved_submodules[-1].tag}")

    _report(reporter, f"Updating {config_fp} version {product}={version}")
    _update_product_version(config_fp, product, version)

    _report(reporter, "Updating source YAML version references")
    update_exit = _run_source_update(product_dir, check=False)
    if update_exit:
        msg = f"{_source_update_label(check=False)} failed for {product_dir} with exit code {update_exit}"
        raise ValueError(msg)
    previous_warning_suppression = _suppress_repeated_config_warnings()
    try:
        _report(reporter, f"Running make all in {_get_schema_build_dir(product_dir)}")
        runner(list(MAKE_ALL_COMMAND), _get_schema_build_dir(product_dir))

        _report(reporter, "Verifying source YAML version references")
        check_exit = _run_source_update(product_dir, check=True)
        if check_exit:
            msg = f"{_source_update_label(check=True)} failed for {product_dir} with exit code {check_exit}"
            raise ValueError(msg)
    finally:
        _restore_repeated_config_warnings(previous_warning_suppression)

    return ReleasePrepSummary(
        product=product,
        version=version,
        product_dir=product_dir,
        submodules=resolved_submodules,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse release-prep CLI arguments.

    :param argv: Optional CLI arguments. Uses ``sys.argv`` when omitted.
    :return: Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(description="Prepare a GKS product schema release.")
    parser.add_argument("--version", required=True, help="Product release version to write to metaschema.yaml.")
    parser.add_argument(
        "--upstream-branch",
        help="Immediate upstream product branch to write to the only submodule in .gitmodules.",
    )
    parser.add_argument(
        "--use-current-upstream-branch",
        action="store_true",
        help="Use the branch already configured for the only submodule in .gitmodules.",
    )
    parser.add_argument(
        "--upstream-tag",
        help=(
            "Optional immediate upstream submodule tag to check out. Requires "
            "--upstream-branch or --use-current-upstream-branch."
        ),
    )
    parser.add_argument(
        "--skip-upstream",
        action="store_true",
        help="Do not update the immediate upstream submodule; use the currently checked out imported product.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate release inputs and print the planned values without changing files.",
    )
    parser.add_argument(
        "--fail-on-dirty",
        action="store_true",
        help="Fail instead of warning when the product repo or upstream submodule has uncommitted changes.",
    )
    return parser.parse_args(argv)


def _print_summary(summary: ReleasePrepSummary) -> None:
    """Print a release-prep summary.

    :param summary: Completed release-prep summary.
    """
    action = "validated" if summary.validated_only else "prepared"
    print(f"{action} {summary.product} {summary.version}")
    for submodule in summary.submodules:
        checkout_label = "would check out" if summary.validated_only else "checked out"
        print(f"submodule {submodule.identifier}: branch {submodule.branch}, {checkout_label} {submodule.tag}")


def main(argv: list[str] | None = None) -> int:
    """Run release prep from CLI arguments.

    :param argv: Optional CLI arguments. Uses ``sys.argv`` when omitted.
    :return: Process exit code.
    """
    args = _parse_args(argv)

    if args.upstream_branch and args.use_current_upstream_branch:
        msg = "Use either --upstream-branch or --use-current-upstream-branch, not both."
        raise ValueError(msg)

    if args.skip_upstream and (args.upstream_branch or args.use_current_upstream_branch or args.upstream_tag):
        msg = "Use --skip-upstream without --upstream-branch, --use-current-upstream-branch, or --upstream-tag."
        raise ValueError(msg)

    if args.upstream_tag and not args.upstream_branch and not args.use_current_upstream_branch:
        msg = "--upstream-tag requires --upstream-branch or --use-current-upstream-branch"
        raise ValueError(msg)

    repo_dir = Path(".").resolve()
    product = _infer_product_from_repo_dir(repo_dir)
    product_dir = _resolve_product_dir(repo_dir, product)
    submodules = None

    if args.upstream_branch:
        submodules = [_infer_submodule_update(product_dir, args.upstream_branch, args.upstream_tag)]
    elif args.use_current_upstream_branch:
        submodules = [_infer_submodule_update_from_current_branch(product_dir, args.upstream_tag)]
    elif not args.skip_upstream:
        _require_upstream_branch_when_submodule_exists(product_dir)

    release_fn = validate_release if args.validate else prepare_release
    summary = release_fn(
        product=product,
        version=args.version,
        repo_dir=repo_dir,
        submodules=submodules,
        reporter=print,
        fail_on_dirty=args.fail_on_dirty,
    )
    _print_summary(summary)
    return 0


def cli() -> None:
    """Console script entry point."""
    try:
        raise SystemExit(main())
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    cli()
