"""Git working-tree and product-branch status checks."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

CommandOutputRunner = Callable[[list[str], Path], str]
Reporter = Callable[[str], None]

GIT_STATUS_PORCELAIN_COMMAND = ("git", "status", "--porcelain")
GIT_UPSTREAM_BRANCH_COMMAND = (
    "git",
    "rev-parse",
    "--abbrev-ref",
    "--symbolic-full-name",
    "@{u}",
)
GIT_UPSTREAM_COUNTS_COMMAND = (
    "git",
    "rev-list",
    "--left-right",
    "--count",
    "HEAD...@{u}",
)


def warn_if_worktree_dirty(
    repo_dir: Path,
    label: str,
    output_runner: CommandOutputRunner,
    reporter: Reporter | None,
) -> None:
    """Report uncommitted changes in a repository without failing.

    :param repo_dir: Git repository directory to inspect.
    :param label: Human-readable repository name for the warning.
    :param output_runner: Command runner used for git output.
    :param reporter: Optional progress reporter.
    :raises subprocess.CalledProcessError: If git status fails.
    """
    status = output_runner(list(GIT_STATUS_PORCELAIN_COMMAND), repo_dir)
    if status and reporter is not None:
        reporter(
            f"Warning: {label} has uncommitted changes. Review the final diff carefully."
        )


def require_clean_worktree(
    repo_dir: Path, label: str, output_runner: CommandOutputRunner
) -> None:
    """Require a Git repository to have no uncommitted changes.

    :param repo_dir: Git repository directory to inspect.
    :param label: Human-readable repository name for the error.
    :param output_runner: Command runner used for git output.
    :raises ValueError: If the repository has uncommitted changes.
    :raises subprocess.CalledProcessError: If git status fails.
    """
    if not output_runner(list(GIT_STATUS_PORCELAIN_COMMAND), repo_dir):
        return

    msg = f"{label} has uncommitted changes. Commit, stash, or discard them before running release prep."
    raise ValueError(msg)


def warn_if_product_branch_not_current(
    repo_dir: Path, output_runner: CommandOutputRunner, reporter: Reporter | None
) -> None:
    """Report when the product branch differs from its tracked upstream.

    This is non-fatal because release prep does not fetch or merge the product
    repository.

    :param repo_dir: Product repository root directory.
    :param output_runner: Command runner used for git output.
    :param reporter: Optional progress reporter.
    """
    try:
        output_runner(list(GIT_UPSTREAM_BRANCH_COMMAND), repo_dir)
        counts = output_runner(list(GIT_UPSTREAM_COUNTS_COMMAND), repo_dir)
    except subprocess.CalledProcessError:
        if reporter is not None:
            reporter(
                "Warning: product branch has no upstream tracking branch; unable to check if it is current."
            )
        return

    ahead_text, _separator, behind_text = counts.partition("\t")
    if not behind_text:
        ahead_text, _separator, behind_text = counts.partition(" ")

    try:
        ahead = int(ahead_text)
        behind = int(behind_text)
    except ValueError:
        if reporter is not None:
            reporter(
                f"Warning: unable to parse product branch upstream status: {counts}"
            )
        return

    if reporter is None:
        return
    if behind and ahead:
        reporter(
            f"Warning: product branch has diverged from upstream ({ahead} ahead, {behind} behind)."
        )
    elif behind:
        reporter(f"Warning: product branch is {behind} commit(s) behind upstream.")
    elif ahead:
        reporter(f"Warning: product branch is {ahead} commit(s) ahead of upstream.")
