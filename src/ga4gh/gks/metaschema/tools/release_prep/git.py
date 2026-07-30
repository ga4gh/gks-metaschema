"""Git submodule metadata and checkout helpers for release preparation.

This module parses and updates ``.gitmodules``, resolves the single immediate
upstream submodule, updates it from its remote branch, and chooses the highest
reachable semantic-version tag. Worktree-status checks live in ``worktree``.
"""

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

from ga4gh.gks.metaschema.tools.release_prep.files import write_text_atomically
from ga4gh.gks.metaschema.tools.release_prep.worktree import (
    CommandOutputRunner,
    Reporter,
    require_clean_worktree,
    warn_if_worktree_dirty,
)

CommandRunner = Callable[[list[str], Path], None]

GITMODULES_FN = ".gitmodules"
ORIGIN_REMOTE = "origin"
SCHEMA_DIR_NAME = "schema"
SUBMODULES_DIR_NAME = "submodules"
GIT_FETCH_ALL_TAGS_COMMAND = ("git", "fetch", "--all", "--tags")

SEMVER_TAG_RE = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)


@dataclass(frozen=True)
class GitmodulesEntry:
    """Location of a submodule entry inside ``.gitmodules``.

    :param gitmodules_fp: Path to the ``.gitmodules`` file.
    :param path_line: Line index of the section's ``path`` key.
    :param branch_line: Line index of the section's ``branch`` key, if present.
    :param name: Submodule section name.
    :param path: Submodule path relative to ``gitmodules_fp.parent``.
    """

    gitmodules_fp: Path
    path_line: int
    branch_line: int | None
    name: str
    path: str


@dataclass(frozen=True)
class SubmoduleUpdate:
    """A requested immediate upstream submodule update.

    :param identifier: Submodule name or path from ``.gitmodules``.
    :param branch: Git branch to write to ``.gitmodules``.
    :param tag: Optional git tag to check out. When omitted, release prep uses
        the highest semantic-version tag reachable from ``origin/<branch>``.
    """

    identifier: str
    branch: str
    tag: str | None = None


def get_product_repo_dir(product_dir: Path) -> Path:
    """Get the product repository root directory.

    :param product_dir: Product schema directory.
    :return: Product repository root directory.
    """
    if product_dir.parent.name == SCHEMA_DIR_NAME:
        return product_dir.parent.parent

    return product_dir.parent


def parse_gitmodules_entries(gitmodules_fp: Path) -> list[GitmodulesEntry]:
    """Parse all submodule entries from a ``.gitmodules`` file.

    :param gitmodules_fp: Candidate ``.gitmodules`` path.
    :return: Parsed entries that have a ``path`` key.
    """
    lines = gitmodules_fp.read_text(encoding="utf-8").splitlines()
    entries: list[GitmodulesEntry] = []
    section_name: str | None = None
    path_line: int | None = None
    branch_line: int | None = None

    def add_current_entry() -> None:
        """Add the active submodule section to ``entries`` when it has a path."""
        if section_name is None or path_line is None:
            return

        path_value = lines[path_line].split("=", maxsplit=1)[1].strip()
        # Parse manually so branch updates preserve existing .gitmodules
        # formatting and comments outside the single line we change.
        entries.append(
            GitmodulesEntry(
                gitmodules_fp=gitmodules_fp,
                path_line=path_line,
                branch_line=branch_line,
                name=section_name,
                path=path_value,
            )
        )

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            add_current_entry()
            section_name = parse_gitmodules_section_name(stripped)
            path_line = None
            branch_line = None
            continue

        if section_name is None:
            continue

        key, separator, _ = stripped.partition("=")

        if not separator:
            continue

        if key.strip() == "path":
            path_line = index
        elif key.strip() == "branch":
            branch_line = index

    add_current_entry()
    return entries


def parse_gitmodules_section_name(section_header: str) -> str | None:
    """Parse a submodule section name from a ``.gitmodules`` header.

    :param section_header: Header line such as ``[submodule "submodules/vrs"]``.
    :return: Section name, or ``None`` for non-submodule sections.
    """
    prefix = '[submodule "'
    suffix = '"]'

    if not section_header.startswith(prefix) or not section_header.endswith(suffix):
        return None

    return section_header[len(prefix) : -len(suffix)]


def identifier_matches_gitmodules_entry(
    identifier: str, entry: GitmodulesEntry
) -> bool:
    """Check whether a CLI submodule identifier matches a ``.gitmodules`` entry.

    :param identifier: Submodule name or path from the CLI.
    :param entry: Parsed ``.gitmodules`` entry.
    :return: ``True`` when the identifier matches section name, path, or path
        basename.
    """
    normalized_identifier = identifier.strip("/")
    normalized_path = entry.path.strip("/")
    return normalized_identifier in {
        entry.name.strip("/"),
        normalized_path,
        Path(normalized_path).name,
    }


def find_gitmodules_entry_for_identifier(
    product_dir: Path, identifier: str
) -> GitmodulesEntry:
    """Find a ``.gitmodules`` entry by submodule name or path.

    :param product_dir: Product schema directory.
    :param identifier: Submodule name or path from the CLI.
    :return: Matching ``.gitmodules`` entry.
    :raises ValueError: If no matching entry is found.
    """
    gitmodules_fp = get_product_repo_dir(product_dir) / GITMODULES_FN
    if gitmodules_fp.exists():
        for entry in parse_gitmodules_entries(gitmodules_fp):
            if identifier_matches_gitmodules_entry(identifier, entry):
                return entry

    msg = f"Could not find a .gitmodules entry for submodule {identifier}"
    raise ValueError(msg)


def find_single_gitmodules_entry(product_dir: Path) -> GitmodulesEntry:
    """Find the single immediate upstream submodule entry.

    Release prep infers the upstream product from ``.gitmodules`` because GKS
    product repositories are expected to contain only one immediate upstream
    submodule.

    :param product_dir: Product schema directory.
    :return: The only submodule entry in ``.gitmodules``.
    :raises ValueError: If ``.gitmodules`` is missing, has no submodule entries,
        or has multiple submodule entries.
    """
    gitmodules_fp = get_product_repo_dir(product_dir) / GITMODULES_FN

    if not gitmodules_fp.exists():
        msg = f"Could not find .gitmodules at {gitmodules_fp}"
        raise ValueError(msg)

    entries = parse_gitmodules_entries(gitmodules_fp)

    if len(entries) == 1:
        return entries[0]

    if not entries:
        msg = f"No submodule entries found in {gitmodules_fp}"
        raise ValueError(msg)

    entry_names = ", ".join(entry.name for entry in entries)
    msg = (
        f"Release prep expected one immediate upstream submodule in {gitmodules_fp}, "
        f"but found {len(entries)}: {entry_names}"
    )
    raise ValueError(msg)


def get_gitmodules_entries(product_dir: Path) -> list[GitmodulesEntry]:
    """Get configured submodule entries for a product repository.

    Missing ``.gitmodules`` means the product has no configured upstream
    submodule, which is valid for the first product in the release chain.

    :param product_dir: Product schema directory.
    :return: Submodule entries parsed from ``.gitmodules``.
    :raises ValueError: If ``.gitmodules`` is missing but a submodules directory
        exists.
    """
    repo_dir = get_product_repo_dir(product_dir)
    gitmodules_fp = repo_dir / GITMODULES_FN

    if not gitmodules_fp.exists():
        submodule_dirs = [
            repo_dir / SUBMODULES_DIR_NAME,
            repo_dir / SCHEMA_DIR_NAME / SUBMODULES_DIR_NAME,
        ]
        existing_submodule_dirs = [
            submodule_dir for submodule_dir in submodule_dirs if submodule_dir.exists()
        ]
        if existing_submodule_dirs:
            paths = ", ".join(str(path) for path in existing_submodule_dirs)
            msg = f"Found submodules directory without .gitmodules at {gitmodules_fp}: {paths}"
            raise ValueError(msg)

        return []

    return parse_gitmodules_entries(gitmodules_fp)


def require_upstream_branch_when_submodule_exists(product_dir: Path) -> None:
    """Require explicit upstream handling when a product has a submodule.

    :param product_dir: Product schema directory.
    :raises ValueError: If the product has a configured submodule but the CLI
        did not say whether to update or skip upstream handling.
    """
    entries = get_gitmodules_entries(product_dir)

    if not entries:
        return

    entry_names = ", ".join(entry.name for entry in entries)
    msg = (
        f"{get_product_repo_dir(product_dir) / GITMODULES_FN} contains upstream submodule "
        f"entry(s): {entry_names}. Provide --upstream-branch, --use-current-upstream-branch, "
        "or --skip-upstream."
    )
    raise ValueError(msg)


def get_gitmodules_branch(entry: GitmodulesEntry) -> str:
    """Get the configured branch for a ``.gitmodules`` entry.

    :param entry: Matching ``.gitmodules`` entry.
    :return: Branch configured for the submodule.
    :raises ValueError: If the submodule entry does not have a ``branch`` key.
    """
    if entry.branch_line is None:
        msg = f"Submodule {entry.name} in {entry.gitmodules_fp} does not have a branch key."
        raise ValueError(msg)

    line = entry.gitmodules_fp.read_text(encoding="utf-8").splitlines()[
        entry.branch_line
    ]
    _key, _separator, branch = line.partition("=")
    branch = branch.strip()

    if branch:
        return branch

    msg = f"Submodule {entry.name} in {entry.gitmodules_fp} has an empty branch value."
    raise ValueError(msg)


def infer_submodule_update(
    product_dir: Path, branch: str, tag: str | None = None
) -> SubmoduleUpdate:
    """Infer the immediate upstream submodule update from ``.gitmodules``.

    Example:
        If ``.gitmodules`` contains only ``schema/submodules/cat-vrs``, branch
        ``1.2.0-ballot.2026-07`` returns a ``SubmoduleUpdate`` for ``cat-vrs``.

    :param product_dir: Product schema directory.
    :param branch: Upstream branch to write to ``.gitmodules``.
    :param tag: Optional upstream tag to check out.
    :return: Requested update for the inferred upstream submodule.
    :raises ValueError: If the upstream submodule cannot be inferred.

    """
    entry = find_single_gitmodules_entry(product_dir)
    return SubmoduleUpdate(identifier=Path(entry.path).name, branch=branch, tag=tag)


def infer_submodule_update_from_current_branch(
    product_dir: Path, tag: str | None = None
) -> SubmoduleUpdate:
    """Infer the upstream submodule update from the current ``.gitmodules`` branch.

    :param product_dir: Product schema directory.
    :param tag: Optional upstream tag to check out.
    :return: Requested update for the inferred upstream submodule and current
        configured branch.
    :raises ValueError: If the upstream submodule or branch cannot be inferred.
    """
    entry = find_single_gitmodules_entry(product_dir)
    return SubmoduleUpdate(
        identifier=Path(entry.path).name, branch=get_gitmodules_branch(entry), tag=tag
    )


def resolve_submodule_entry(
    product_dir: Path, submodule: SubmoduleUpdate
) -> tuple[GitmodulesEntry, Path]:
    """Resolve a submodule entry and directory from ``.gitmodules``.

    :param product_dir: Product schema directory.
    :param submodule: Requested submodule update.
    :return: Matching ``.gitmodules`` entry and resolved submodule directory.
    :raises ValueError: If no matching ``.gitmodules`` entry is found.
    """
    entry = find_gitmodules_entry_for_identifier(product_dir, submodule.identifier)
    return entry, (entry.gitmodules_fp.parent / entry.path).resolve()


def update_gitmodules_branch(entry: GitmodulesEntry, branch: str) -> None:
    """Set the configured branch for a submodule in ``.gitmodules``.

    The function mutates the matching ``.gitmodules`` file. If the matching
    entry does not already have a ``branch`` key, one is added below ``path``.

    :param entry: Matching ``.gitmodules`` entry.
    :param branch: Branch to write.
    """
    lines = entry.gitmodules_fp.read_text(encoding="utf-8").splitlines()
    branch_line = f"\tbranch = {branch}"

    if entry.branch_line is None:
        lines.insert(entry.path_line + 1, branch_line)
    else:
        lines[entry.branch_line] = branch_line

    write_text_atomically(entry.gitmodules_fp, "\n".join(lines) + "\n")


def require_submodule_dir(entry: GitmodulesEntry) -> Path:
    """Require the configured submodule checkout to exist locally.

    :param entry: Matching ``.gitmodules`` entry.
    :return: Resolved submodule directory.
    :raises ValueError: If the submodule checkout does not exist.
    """
    submodule_dir = (entry.gitmodules_fp.parent / entry.path).resolve()

    if submodule_dir.is_dir():
        return submodule_dir

    msg = (
        f"Submodule directory for {entry.name} does not exist after update: {submodule_dir}. "
        f"Run git submodule update --remote --init -- {entry.path} from {entry.gitmodules_fp.parent}."
    )
    raise ValueError(msg)


def update_submodule_from_remote(entry: GitmodulesEntry, runner: CommandRunner) -> None:
    """Initialize and update a submodule from its configured remote branch.

    :param entry: Matching ``.gitmodules`` entry.
    :param runner: Command runner used for git commands.
    :raises subprocess.CalledProcessError: If git submodule update fails.
    """
    runner(
        ["git", "submodule", "update", "--remote", "--init", "--", entry.path],
        entry.gitmodules_fp.parent,
    )


def initialize_submodule(entry: GitmodulesEntry, runner: CommandRunner) -> None:
    """Initialize a missing submodule without updating its configured branch.

    :param entry: Matching ``.gitmodules`` entry.
    :param runner: Command runner used for git commands.
    :raises subprocess.CalledProcessError: If submodule initialization fails.
    """
    runner(
        ["git", "submodule", "update", "--init", "--", entry.path],
        entry.gitmodules_fp.parent,
    )


def _normalize_semantic_tag_for_version(tag: str) -> Version | None:
    """Normalize a semantic-version git tag into a sortable ``Version``.

    Examples:
        ``v1.2.0`` returns ``Version("1.2.0")``. A SemVer prerelease tag such
        as ``v1.2.0-ballot.2026-07.1`` is converted to a PEP 440-compatible
        development version so it can be ordered by ``packaging``.

    :param tag: Git tag name.
    :return: Sortable version, or ``None`` for non-semver tags.

    """
    match = SEMVER_TAG_RE.match(tag)

    if match is None:
        return None

    prerelease = match.group("prerelease")
    normalized = f"{match.group('major')}.{match.group('minor')}.{match.group('patch')}"

    if prerelease:
        local_label = re.sub(r"[^0-9A-Za-z.]+", ".", prerelease).strip(".")
        normalized = f"{normalized}.dev0+{local_label}"

    try:
        return Version(normalized)
    except InvalidVersion:
        return None


def select_highest_semantic_tag(
    tags: list[str], submodule: SubmoduleUpdate, branch_ref: str
) -> str:
    """Select the highest semantic-version tag from reachable git tags.

    :param tags: Git tags reachable from the upstream branch.
    :param submodule: Requested submodule update.
    :param branch_ref: Remote branch ref inspected for reachable tags.
    :return: Highest semantic-version tag, preserving the original tag text.
    :raises ValueError: If no semantic-version tags are found.
    """
    semantic_tags = [
        (version, tag)
        for tag in tags
        if (version := _normalize_semantic_tag_for_version(tag)) is not None
    ]

    if semantic_tags:
        return max(semantic_tags, key=lambda version_and_tag: version_and_tag[0])[1]

    msg = f"Could not find a semantic-version git tag for submodule {submodule.identifier} on branch {branch_ref}"
    raise ValueError(msg)


def get_latest_reachable_tag(
    submodule: SubmoduleUpdate,
    branch_ref: str,
    submodule_dir: Path,
    output_runner: CommandOutputRunner,
) -> str:
    """Get the highest semantic-version tag reachable from a submodule branch.

    Example:
        On branch ``origin/1.2.0-ballot.2026-07``, this may return
        ``v1.2.0-ballot.2026-07.1``.

    :param submodule: Requested submodule update.
    :param branch_ref: Remote branch ref to inspect.
    :param submodule_dir: Resolved submodule directory.
    :param output_runner: Command runner used for git output.
    :return: Highest semantic-version reachable tag.
    :raises ValueError: If no reachable tag can be found.

    """
    try:
        output = output_runner(["git", "tag", "--merged", branch_ref], submodule_dir)
    except subprocess.CalledProcessError as exc:
        msg = f"Could not find a reachable git tag for submodule {submodule.identifier} on branch {submodule.branch}"
        raise ValueError(msg) from exc

    return select_highest_semantic_tag(output.splitlines(), submodule, branch_ref)


def resolve_branch_ref(
    submodule: SubmoduleUpdate, submodule_dir: Path, runner: CommandRunner
) -> str:
    """Resolve a submodule branch to its remote git ref.

    :param submodule: Requested submodule update.
    :param submodule_dir: Resolved submodule directory.
    :param runner: Command runner used for git validation commands.
    :return: ``origin/<branch>``.
    :raises ValueError: If the remote branch ref does not exist.
    """
    branch_ref = f"{ORIGIN_REMOTE}/{submodule.branch}"
    try:
        runner(
            ["git", "rev-parse", "--verify", f"{branch_ref}^{{commit}}"], submodule_dir
        )
    except subprocess.CalledProcessError as exc:
        msg = f"Could not find git branch {branch_ref} for submodule {submodule.identifier} in {submodule_dir}"
        raise ValueError(msg) from exc

    return branch_ref


def validate_submodule(
    submodule: SubmoduleUpdate,
    product_dir: Path,
    runner: CommandRunner,
    output_runner: CommandOutputRunner,
    reporter: Reporter | None = None,
    fail_on_dirty: bool = False,
    check_clean: bool = True,
) -> tuple[Path, GitmodulesEntry, SubmoduleUpdate]:
    """Validate an immediate upstream submodule update without mutating files.

    :param submodule: Requested submodule update.
    :param product_dir: Product schema directory containing ``metaschema.yaml``.
    :param runner: Command runner used for git validation commands.
    :param output_runner: Command runner used for git output.
    :param reporter: Optional progress reporter for dirty worktree warnings.
    :param fail_on_dirty: Whether dirty submodule worktrees should fail
        validation instead of printing warnings.
    :param check_clean: Whether to check the submodule working tree for
        uncommitted changes.
    :return: Resolved submodule directory, ``.gitmodules`` entry, and update
        with the resolved tag.
    :raises ValueError: If the submodule directory, ``.gitmodules`` entry, or
        requested branch or tag cannot be found.
    """
    entry, submodule_dir = resolve_submodule_entry(product_dir, submodule)
    if not submodule_dir.is_dir():
        msg = (
            f"Submodule directory for {submodule.identifier} does not exist: {submodule_dir}. "
            f"Run git submodule update --init -- {entry.path} from {entry.gitmodules_fp.parent}."
        )
        raise ValueError(msg)

    if check_clean and fail_on_dirty:
        require_clean_worktree(
            submodule_dir, f"Submodule {submodule.identifier}", output_runner
        )
    elif check_clean:
        warn_if_worktree_dirty(
            submodule_dir, f"Submodule {submodule.identifier}", output_runner, reporter
        )

    branch_ref = resolve_branch_ref(submodule, submodule_dir, runner)
    tag = submodule.tag or get_latest_reachable_tag(
        submodule, branch_ref, submodule_dir, output_runner
    )

    try:
        runner(["git", "rev-parse", "--verify", f"{tag}^{{commit}}"], submodule_dir)
    except subprocess.CalledProcessError as exc:
        msg = f"Could not find git tag {tag} for submodule {submodule.identifier} in {submodule_dir}"
        raise ValueError(msg) from exc

    return (
        submodule_dir,
        entry,
        SubmoduleUpdate(
            identifier=submodule.identifier, branch=submodule.branch, tag=tag
        ),
    )


def update_submodule(
    submodule: SubmoduleUpdate,
    product_dir: Path,
    runner: CommandRunner,
    output_runner: CommandOutputRunner,
    reporter: Reporter | None = None,
    fail_on_dirty: bool = False,
) -> SubmoduleUpdate:
    """Resolve an upstream ref before updating metadata and checking it out.

    The branch and tag are fetched and resolved before ``.gitmodules`` changes.
    A failed ref lookup therefore leaves tracked product files unchanged.

    :param submodule: Requested submodule update.
    :param product_dir: Product schema directory containing ``metaschema.yaml``.
    :param runner: Command runner used for git commands.
    :param output_runner: Command runner used for git output.
    :param reporter: Optional progress reporter for dirty worktree warnings.
    :param fail_on_dirty: Whether dirty submodule worktrees should fail release
        prep instead of printing warnings.
    :return: Submodule update with the resolved checkout tag.
    :raises ValueError: If the submodule directory, ``.gitmodules`` entry, or
        requested branch or tag cannot be found.
    """
    entry, submodule_dir = resolve_submodule_entry(product_dir, submodule)
    if not submodule_dir.is_dir():
        initialize_submodule(entry, runner)
    submodule_dir = require_submodule_dir(entry)
    if fail_on_dirty:
        require_clean_worktree(
            submodule_dir, f"Submodule {submodule.identifier}", output_runner
        )
    else:
        warn_if_worktree_dirty(
            submodule_dir, f"Submodule {submodule.identifier}", output_runner, reporter
        )
    runner(list(GIT_FETCH_ALL_TAGS_COMMAND), submodule_dir)
    _submodule_dir, _entry, resolved_submodule = validate_submodule(
        submodule,
        product_dir,
        runner,
        output_runner,
        reporter=reporter,
        fail_on_dirty=fail_on_dirty,
        check_clean=False,
    )

    if resolved_submodule.tag is None:
        msg = f"Could not resolve git tag for submodule {submodule.identifier}"
        raise ValueError(msg)
    update_gitmodules_branch(entry, submodule.branch)
    update_submodule_from_remote(entry, runner)
    runner(["git", "checkout", resolved_submodule.tag], submodule_dir)
    return resolved_submodule
