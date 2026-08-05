"""Prepare a GKS product schema release from metaschema configuration.

The release-prep command orchestrates the repeatable release steps that product
maintainers otherwise run manually: update the immediate upstream submodule
branch, validate the selected upstream tag, set the local product version,
regenerate artifacts, and verify source YAML version references.
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ga4gh.gks.metaschema.tools.config import (
    METASCHEMA_FN,
    SUPPRESS_UNSUPPORTED_KEY_WARNING_ENV,
    load_metaschema_config,
)
from ga4gh.gks.metaschema.tools.release_prep import (
    git,
    product_config,
    schema_versions,
    worktree,
)

SOURCE_UPDATE_CHECK_FLAG = "--check"
SOURCE_UPDATE_DISALLOW_VERSIONED_REFS_FLAG = "--disallow-versioned-refs"
SOURCE_UPDATE_COMMAND_NAME = "source2updated"
MAKE_ALL_COMMAND = ("make", "all")
MAKE_CLEAN_COMMAND = ("make", "clean")


def _run_command(command: list[str], cwd: Path) -> None:
    """Run a command for release prep.

    :param command: Command and arguments to run.
    :param cwd: Working directory for the command.
    :raises subprocess.CalledProcessError: If the command exits with a
        non-zero status.
    """
    # Commands are constructed by release-prep helpers and run without a shell.
    subprocess.run(command, cwd=cwd, check=True)  # noqa: S603


def _run_command_output(command: list[str], cwd: Path) -> str:
    """Run a command and return standard output.

    :param command: Command and arguments to run.
    :param cwd: Working directory for the command.
    :return: Command standard output with surrounding whitespace removed.
    :raises subprocess.CalledProcessError: If the command exits with a
        non-zero status.
    """
    # Commands are constructed by release-prep helpers and run without a shell.
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
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
    submodules: list[git.SubmoduleUpdate]
    validated_only: bool = False


def _start_release(
    action: str,
    product: str,
    version: str,
    repo_dir: Path,
    submodules: list[git.SubmoduleUpdate],
    output_runner: worktree.CommandOutputRunner,
    reporter: worktree.Reporter | None,
    fail_on_dirty: bool,
) -> Path:
    """Validate common release inputs and return the product schema directory.

    :param action: Present-tense action shown in progress messages.
    :param product: Local product name and version key.
    :param version: Requested local product version.
    :param repo_dir: Product repository root directory.
    :param submodules: Requested immediate upstream submodule updates.
    :param output_runner: Command runner for git commands that return output.
    :param reporter: Optional progress reporter.
    :param fail_on_dirty: Whether dirty worktrees should fail the operation.
    :return: Resolved product schema directory.
    :raises ValueError: If more than one submodule is requested or the product
        directory cannot be resolved.
    """
    _validate_submodule_count(submodules)
    _report(reporter, f"{action} release for product {product} version {version}")
    product_dir = product_config.resolve_product_dir(repo_dir, product)
    _report(reporter, f"Using product schema: {product_dir}")
    _handle_dirty_worktree(
        git.get_product_repo_dir(product_dir),
        f"Product {product}",
        output_runner,
        reporter,
        fail_on_dirty,
    )
    _warn_if_downstream_branch_not_current(
        product_dir, submodules, output_runner, reporter
    )
    return product_dir


def _report(reporter: worktree.Reporter | None, message: str) -> None:
    """Report release-prep progress when a reporter is configured.

    :param reporter: Optional progress reporter, such as ``print``.
    :param message: Message to report.
    """
    if reporter is not None:
        reporter(message)


def _run_source_update(product_dir: Path, check: bool) -> int:
    """Run source version management for a product directory.

    :param product_dir: Product schema directory.
    :param check: Whether to run in check mode.
    :return: Exit code from ``source2updated``.
    """
    argv = [SOURCE_UPDATE_DISALLOW_VERSIONED_REFS_FLAG, str(product_dir)]

    if check:
        argv.insert(0, SOURCE_UPDATE_CHECK_FLAG)

    return schema_versions.main(argv)


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


def _validate_submodule_count(submodules: list[git.SubmoduleUpdate]) -> None:
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
    submodules: list[git.SubmoduleUpdate],
    output_runner: worktree.CommandOutputRunner,
    reporter: worktree.Reporter | None,
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

    worktree.warn_if_product_branch_not_current(
        git.get_product_repo_dir(product_dir), output_runner, reporter
    )


def _handle_dirty_worktree(
    repo_dir: Path,
    label: str,
    output_runner: worktree.CommandOutputRunner,
    reporter: worktree.Reporter | None,
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
        worktree.require_clean_worktree(repo_dir, label, output_runner)
        return

    worktree.warn_if_worktree_dirty(repo_dir, label, output_runner, reporter)


def validate_release(
    product: str,
    version: str,
    repo_dir: Path = Path(),
    submodules: list[git.SubmoduleUpdate] | None = None,
    runner: git.CommandRunner = _run_command,
    output_runner: worktree.CommandOutputRunner = _run_command_output,
    reporter: worktree.Reporter | None = None,
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
    product_dir = _start_release(
        "Validating",
        product,
        version,
        repo_dir,
        requested_submodules,
        output_runner,
        reporter,
        fail_on_dirty,
    )
    load_metaschema_config(product_dir / METASCHEMA_FN)
    resolved_submodules: list[git.SubmoduleUpdate] = []

    for submodule in requested_submodules:
        _report(
            reporter,
            f"Validating submodule {submodule.identifier} on branch {submodule.branch}",
        )
        _submodule_dir, _entry, resolved_submodule = git.validate_submodule(
            submodule,
            product_dir,
            runner,
            output_runner,
            reporter=reporter,
            fail_on_dirty=fail_on_dirty,
        )
        _report(
            reporter,
            f"Resolved submodule {submodule.identifier} tag {resolved_submodule.tag}",
        )
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
    repo_dir: Path = Path(),
    submodules: list[git.SubmoduleUpdate] | None = None,
    runner: git.CommandRunner = _run_command,
    output_runner: worktree.CommandOutputRunner = _run_command_output,
    reporter: worktree.Reporter | None = None,
    fail_on_dirty: bool = False,
) -> ReleasePrepSummary:
    """Prepare source and generated files for a product release.

    The function mutates the product ``metaschema.yaml`` by setting the local
    product version, may update the immediate upstream git submodule, updates
    source YAML version references before build validation runs, runs
    ``make clean`` and ``make all`` to regenerate artifacts, then verifies the source YAML files
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
    product_dir = _start_release(
        "Preparing",
        product,
        version,
        repo_dir,
        requested_submodules,
        output_runner,
        reporter,
        fail_on_dirty,
    )
    config_fp = product_dir / METASCHEMA_FN
    resolved_submodules: list[git.SubmoduleUpdate] = []

    for submodule in requested_submodules:
        _report(
            reporter,
            f"Updating submodule {submodule.identifier} on branch {submodule.branch}",
        )
        resolved_submodules.append(
            git.update_submodule(
                submodule,
                product_dir,
                runner,
                output_runner,
                reporter=reporter,
                fail_on_dirty=fail_on_dirty,
            )
        )
        _report(
            reporter,
            f"Resolved submodule {submodule.identifier} tag {resolved_submodules[-1].tag}",
        )

    _report(reporter, f"Updating {config_fp} version {product}={version}")
    product_config.update_product_version(config_fp, product, version)

    _report(reporter, "Updating source YAML version references")
    update_exit = _run_source_update(product_dir, check=False)
    if update_exit:
        msg = f"{_source_update_label(check=False)} failed for {product_dir} with exit code {update_exit}"
        raise ValueError(msg)
    previous_warning_suppression = _suppress_repeated_config_warnings()
    try:
        build_dir = product_config.get_schema_build_dir(product_dir)
        _report(reporter, f"Running make clean in {build_dir}")
        runner(list(MAKE_CLEAN_COMMAND), build_dir)
        _report(reporter, f"Running make all in {build_dir}")
        runner(list(MAKE_ALL_COMMAND), build_dir)

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
    parser = argparse.ArgumentParser(
        description="Prepare a GKS product schema release."
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Product release version to write to metaschema.yaml.",
    )
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
            "Optional immediate upstream submodule tag to validate. Requires "
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
    print(f"{action} {summary.product} {summary.version}")  # noqa: T201
    for submodule in summary.submodules:
        tag_label = "would resolve" if summary.validated_only else "resolved"
        print(  # noqa: T201
            f"submodule {submodule.identifier}: branch {submodule.branch}, {tag_label} {submodule.tag}"
        )


def main(argv: list[str] | None = None) -> int:
    """Run release prep from CLI arguments.

    :param argv: Optional CLI arguments. Uses ``sys.argv`` when omitted.
    :return: Process exit code.
    """
    args = _parse_args(argv)

    if args.upstream_branch and args.use_current_upstream_branch:
        msg = "Use either --upstream-branch or --use-current-upstream-branch, not both."
        raise ValueError(msg)

    if args.skip_upstream and (
        args.upstream_branch or args.use_current_upstream_branch or args.upstream_tag
    ):
        msg = "Use --skip-upstream without --upstream-branch, --use-current-upstream-branch, or --upstream-tag."
        raise ValueError(msg)

    if (
        args.upstream_tag
        and not args.upstream_branch
        and not args.use_current_upstream_branch
    ):
        msg = (
            "--upstream-tag requires --upstream-branch or --use-current-upstream-branch"
        )
        raise ValueError(msg)

    repo_dir = Path.cwd()
    product = product_config.infer_product_from_repo_dir(repo_dir)
    product_dir = product_config.resolve_product_dir(repo_dir, product)
    submodules = None

    if args.upstream_branch:
        submodules = [
            git.infer_submodule_update(
                product_dir, args.upstream_branch, args.upstream_tag
            )
        ]
    elif args.use_current_upstream_branch:
        submodules = [
            git.infer_submodule_update_from_current_branch(
                product_dir, args.upstream_tag
            )
        ]
    elif not args.skip_upstream:
        git.require_upstream_branch_when_submodule_exists(product_dir)

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
        print(exc, file=sys.stderr)  # noqa: T201
        raise SystemExit(1) from exc


if __name__ == "__main__":
    cli()
