"""Tests for release-prep workflow orchestration."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from ga4gh.gks.metaschema.scripts import release_prep
from ga4gh.gks.metaschema.scripts.release_prep import (
    SubmoduleUpdate,
    main,
    prepare_release,
    validate_release,
)
from ga4gh.gks.metaschema.scripts.release_prep_git import select_highest_semantic_tag

FIXTURE_ROOT = Path(__file__).parent / "data" / "schema" / "cases" / "release-prep"


def _copy_release_fixture(tmp_path: Path) -> Path:
    """Copy release-prep fixture data into a mutable temporary directory.

    :param tmp_path: Pytest temporary directory.
    :return: Copied fixture root.
    """
    workdir = tmp_path / "release-prep"
    shutil.copytree(FIXTURE_ROOT, workdir)
    return workdir


def _clean_output(command: list[str], cwd: Path) -> str:
    """Return clean git status output for tests that use explicit tags."""
    if command == ["git", "status", "--porcelain"]:
        return ""
    if command == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
        return "origin/main"
    if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
        return "0\t0"
    msg = f"unexpected output command: {command} in {cwd}"
    raise AssertionError(msg)


def _run_fixture_make_all(command: list[str], cwd: Path, product_dir: Path) -> None:
    """Model the source update performed by the product ``make all`` target.

    :param command: Command passed to the fake runner.
    :param cwd: Command working directory.
    :param product_dir: Product schema directory to update.
    """
    if command != ["make", "all"]:
        return

    assert cwd == product_dir.parent.resolve()
    exit_code = release_prep._run_source_update(product_dir.resolve(), check=False)  # noqa: SLF001
    assert exit_code == 0


def test_select_highest_semantic_tag_uses_packaging_version_order() -> None:
    """Select the highest semantic-version tag while preserving the git tag text."""
    tag = select_highest_semantic_tag(
        [
            "not-a-version",
            "v2.2.0-ballot.2026-07.1",
            "v2.1.9",
            "v2.2.0-ballot.2026-07.2",
        ],
        SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot"),
        "origin/2.2.0-ballot",
    )

    assert tag == "v2.2.0-ballot.2026-07.2"


def test_select_highest_semantic_tag_supports_ballot_versions() -> None:
    """Support GKS ballot tag versions that are not directly PEP 440-compatible."""
    tag = select_highest_semantic_tag(
        ["v1.2.0-ballot.2026-07.1", "v1.2.0-ballot.2026-07.2"],
        SubmoduleUpdate(identifier="cat-vrs", branch="1.2.0-ballot.2026-07"),
        "origin/1.2.0-ballot.2026-07",
    )

    assert tag == "v1.2.0-ballot.2026-07.2"


def test_prepare_release_updates_versions_and_runs_release_commands(
    tmp_path: Path,
) -> None:
    """Prepare a release and verify the expected workspace mutations and commands."""
    workdir = _copy_release_fixture(tmp_path)
    commands: list[tuple[list[str], Path]] = []
    messages: list[str] = []

    def runner(command: list[str], cwd: Path) -> None:
        """Record release commands instead of running git or make."""
        commands.append((command, cwd))
        if command == ["make", "all"]:
            source = (
                workdir / "schema" / "example" / "module" / "example-source.yaml"
            ).read_text(encoding="utf-8")
            assert (
                "https://w3id.org/ga4gh/schema/example/1.1.0/module/example-source.yaml"
                in source
            )
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return the latest reachable tag for the submodule branch."""
        commands.append((command, cwd))
        if command == ["git", "status", "--porcelain"]:
            return ""
        if command == [
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]:
            return "origin/main"
        if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
            return "0\t0"
        if command == ["git", "tag", "--merged", "origin/2.2.0-ballot"]:
            return "v2.1.0\nv2.2.0-ballot.2026-07.1\nv2.2.0\nnot-a-version"
        msg = f"unexpected output command: {command} in {cwd}"
        raise AssertionError(msg)

    summary = prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
        runner=runner,
        output_runner=output_runner,
        reporter=messages.append,
    )

    config = yaml.safe_load(
        (workdir / "schema" / "example" / "metaschema.yaml").read_text(encoding="utf-8")
    )
    source = (
        workdir / "schema" / "example" / "module" / "example-source.yaml"
    ).read_text(encoding="utf-8")
    gitmodules = (workdir / ".gitmodules").read_text(encoding="utf-8")
    submodule_dir = (workdir / "schema" / "submodules" / "vrs").resolve()

    assert config["versions"]["example"] == "1.1.0"
    assert (
        "https://w3id.org/ga4gh/schema/example/1.1.0/module/example-source.yaml"
        in source
    )
    assert "\tbranch = 2.2.0-ballot" in gitmodules
    assert summary.product == "example"
    assert summary.version == "1.1.0"
    assert summary.submodules == [
        SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0")
    ]
    assert messages == [
        "Preparing release for product example version 1.1.0",
        f"Using product schema: {(workdir / 'schema' / 'example').resolve()}",
        "Updating submodule vrs on branch 2.2.0-ballot",
        "Checked out submodule vrs tag v2.2.0",
        f"Updating {(workdir / 'schema' / 'example' / 'metaschema.yaml').resolve()} version example=1.1.0",
        "Updating source YAML version references",
        f"Running make all in {(workdir / 'schema').resolve()}",
        "Verifying source YAML version references",
    ]
    assert commands == [
        (["git", "status", "--porcelain"], workdir.resolve()),
        (
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            workdir.resolve(),
        ),
        (
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            workdir.resolve(),
        ),
        (
            [
                "git",
                "submodule",
                "update",
                "--remote",
                "--init",
                "--",
                "schema/submodules/vrs",
            ],
            workdir.resolve(),
        ),
        (["git", "status", "--porcelain"], submodule_dir),
        (["git", "fetch", "--all", "--tags"], submodule_dir),
        (
            ["git", "rev-parse", "--verify", "origin/2.2.0-ballot^{commit}"],
            submodule_dir,
        ),
        (["git", "tag", "--merged", "origin/2.2.0-ballot"], submodule_dir),
        (["git", "rev-parse", "--verify", "v2.2.0^{commit}"], submodule_dir),
        (["git", "checkout", "v2.2.0"], submodule_dir),
        (["make", "all"], (workdir / "schema").resolve()),
    ]


def test_prepare_release_uses_explicit_submodule_tag(tmp_path: Path) -> None:
    """Use an explicit checkout tag instead of discovering the latest tag."""
    workdir = _copy_release_fixture(tmp_path)
    commands: list[tuple[list[str], Path]] = []

    def runner(command: list[str], cwd: Path) -> None:
        """Record release commands instead of running git or make."""
        commands.append((command, cwd))
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    def output_runner(command: list[str], cwd: Path) -> str:
        """Fail if release prep tries to discover a tag."""
        if command == ["git", "status", "--porcelain"]:
            return ""
        if command == [
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]:
            return "origin/main"
        if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
            return "0\t0"
        msg = f"unexpected output command: {command} in {cwd}"
        raise AssertionError(msg)

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[
            SubmoduleUpdate(
                identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0-ballot.2026-07.1"
            )
        ],
        runner=runner,
        output_runner=output_runner,
    )

    submodule_dir = (workdir / "schema" / "submodules" / "vrs").resolve()

    assert commands[:5] == [
        (
            [
                "git",
                "submodule",
                "update",
                "--remote",
                "--init",
                "--",
                "schema/submodules/vrs",
            ],
            workdir.resolve(),
        ),
        (["git", "fetch", "--all", "--tags"], submodule_dir),
        (
            ["git", "rev-parse", "--verify", "origin/2.2.0-ballot^{commit}"],
            submodule_dir,
        ),
        (
            ["git", "rev-parse", "--verify", "v2.2.0-ballot.2026-07.1^{commit}"],
            submodule_dir,
        ),
        (["git", "checkout", "v2.2.0-ballot.2026-07.1"], submodule_dir),
    ]


def test_prepare_release_can_reject_dirty_product_repo(tmp_path: Path) -> None:
    """Reject a dirty product repo when strict dirty-worktree mode is enabled."""
    workdir = _copy_release_fixture(tmp_path)

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return dirty status for the product repo."""
        if command == ["git", "status", "--porcelain"]:
            return " M schema/example/metaschema.yaml"

        msg = f"unexpected output command: {command} in {cwd}"
        raise AssertionError(msg)

    with pytest.raises(ValueError, match="Product example has uncommitted changes"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
            output_runner=output_runner,
            fail_on_dirty=True,
        )


def test_prepare_release_can_reject_dirty_submodule(tmp_path: Path) -> None:
    """Reject a dirty upstream submodule when strict dirty-worktree mode is enabled."""
    workdir = _copy_release_fixture(tmp_path)
    submodule_dir = (workdir / "schema" / "submodules" / "vrs").resolve()

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return dirty status for the submodule only."""
        if command == ["git", "status", "--porcelain"] and cwd == submodule_dir:
            return " M schema/vrs/vrs-source.yaml"
        if command == ["git", "status", "--porcelain"]:
            return ""
        if command == [
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]:
            return "origin/main"
        if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
            return "0\t0"

        msg = f"unexpected output command: {command} in {cwd}"
        raise AssertionError(msg)

    def runner(command: list[str], cwd: Path) -> None:
        """Do not run git commands for this test."""

    with pytest.raises(ValueError, match="Submodule vrs has uncommitted changes"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
            runner=runner,
            output_runner=output_runner,
            fail_on_dirty=True,
        )


def test_prepare_release_warns_for_dirty_product_repo_by_default(
    tmp_path: Path,
) -> None:
    """Warn and continue when the product repo is dirty by default."""
    repo_dir = tmp_path / "gks-core"
    product_dir = repo_dir / "schema" / "gks-core"
    product_dir.mkdir(parents=True)
    (product_dir / "metaschema.yaml").write_text(
        "versions:\n  gks-core: 3.0.0\n", encoding="utf-8"
    )
    messages: list[str] = []

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return dirty status for the product repo."""
        if command == ["git", "status", "--porcelain"]:
            return " M schema/gks-core/metaschema.yaml"
        msg = f"unexpected output command: {command} in {cwd}"
        raise AssertionError(msg)

    def runner(command: list[str], cwd: Path) -> None:
        """Do not run make for this test."""

    prepare_release(
        product="gks-core",
        version="3.0.0",
        repo_dir=repo_dir,
        submodules=None,
        runner=runner,
        output_runner=output_runner,
        reporter=messages.append,
    )

    assert (
        "Warning: Product gks-core has uncommitted changes. Review the final diff carefully."
        in messages
    )


def test_prepare_release_warns_for_dirty_submodule_by_default(tmp_path: Path) -> None:
    """Warn and continue when the upstream submodule is dirty by default."""
    workdir = _copy_release_fixture(tmp_path)
    submodule_dir = (workdir / "schema" / "submodules" / "vrs").resolve()
    messages: list[str] = []

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return dirty status for the submodule only."""
        if command == ["git", "status", "--porcelain"] and cwd == submodule_dir:
            return " M schema/vrs/vrs-source.yaml"
        if command == ["git", "status", "--porcelain"]:
            return ""
        if command == [
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]:
            return "origin/main"
        if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
            return "0\t0"

        msg = f"unexpected output command: {command} in {cwd}"
        raise AssertionError(msg)

    def runner(command: list[str], cwd: Path) -> None:
        """Model make all without running git or make commands."""
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[
            SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0")
        ],
        runner=runner,
        output_runner=output_runner,
        reporter=messages.append,
    )

    assert (
        "Warning: Submodule vrs has uncommitted changes. Review the final diff carefully."
        in messages
    )


def test_prepare_release_warns_when_product_branch_is_behind(tmp_path: Path) -> None:
    """Warn, without failing, when the product branch is behind its upstream."""
    workdir = _copy_release_fixture(tmp_path)
    messages: list[str] = []

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return a clean but behind product branch state."""
        if command == ["git", "status", "--porcelain"]:
            return ""
        if command == [
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]:
            return "origin/main"
        if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
            return "0\t2"
        msg = f"unexpected output command: {command} in {cwd}"
        raise AssertionError(msg)

    def runner(command: list[str], cwd: Path) -> None:
        """Do not run git or make commands for this test."""
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[
            SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0")
        ],
        runner=runner,
        output_runner=output_runner,
        reporter=messages.append,
    )

    assert "Warning: product branch is 2 commit(s) behind upstream." in messages


def test_prepare_release_skips_branch_warning_for_product_without_submodule(
    tmp_path: Path,
) -> None:
    """Do not warn about upstream branch freshness for first-chain products."""
    repo_dir = tmp_path / "gks-core"
    product_dir = repo_dir / "schema" / "gks-core"
    product_dir.mkdir(parents=True)
    (product_dir / "metaschema.yaml").write_text(
        "versions:\n  gks-core: 3.0.0\n",
        encoding="utf-8",
    )
    messages: list[str] = []
    commands: list[tuple[list[str], Path]] = []

    def runner(command: list[str], cwd: Path) -> None:
        """Record the build command without running make."""
        commands.append((command, cwd))

    def output_runner(command: list[str], cwd: Path) -> str:
        """Only allow the clean worktree check."""
        commands.append((command, cwd))
        if command == ["git", "status", "--porcelain"]:
            return ""
        msg = f"unexpected output command: {command} in {cwd}"
        raise AssertionError(msg)

    prepare_release(
        product="gks-core",
        version="3.0.0",
        repo_dir=repo_dir,
        submodules=None,
        runner=runner,
        output_runner=output_runner,
        reporter=messages.append,
    )

    assert not any(
        message.startswith("Warning: product branch") for message in messages
    )
    assert (["git", "status", "--porcelain"], repo_dir.resolve()) in commands
    assert all("@{u}" not in command for command, _cwd in commands)


def test_prepare_release_initializes_missing_submodule(tmp_path: Path) -> None:
    """Initialize a configured submodule checkout when it is missing locally."""
    workdir = _copy_release_fixture(tmp_path)
    submodule_dir = workdir / "schema" / "submodules" / "vrs"
    shutil.rmtree(submodule_dir)
    commands: list[tuple[list[str], Path]] = []

    def runner(command: list[str], cwd: Path) -> None:
        """Record commands and create the submodule directory on init."""
        commands.append((command, cwd))
        if command == [
            "git",
            "submodule",
            "update",
            "--remote",
            "--init",
            "--",
            "schema/submodules/vrs",
        ]:
            submodule_dir.mkdir(parents=True)
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[
            SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0")
        ],
        runner=runner,
        output_runner=_clean_output,
    )

    assert commands[:5] == [
        (
            [
                "git",
                "submodule",
                "update",
                "--remote",
                "--init",
                "--",
                "schema/submodules/vrs",
            ],
            workdir.resolve(),
        ),
        (["git", "fetch", "--all", "--tags"], submodule_dir),
        (
            ["git", "rev-parse", "--verify", "origin/2.2.0-ballot^{commit}"],
            submodule_dir,
        ),
        (["git", "rev-parse", "--verify", "v2.2.0^{commit}"], submodule_dir),
        (["git", "checkout", "v2.2.0"], submodule_dir),
    ]


def test_validate_release_reports_values_without_mutating_files(tmp_path: Path) -> None:
    """Validate release inputs without updating files or running release commands."""
    workdir = _copy_release_fixture(tmp_path)
    commands: list[tuple[list[str], Path]] = []

    def runner(command: list[str], cwd: Path) -> None:
        """Record validation commands."""
        commands.append((command, cwd))

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return the latest reachable tag for validation."""
        commands.append((command, cwd))
        if command == ["git", "status", "--porcelain"]:
            return ""
        if command == [
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]:
            return "origin/main"
        if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
            return "0\t0"
        if command == ["git", "tag", "--merged", "origin/2.2.0-ballot"]:
            return "v2.1.0\nv2.2.0"

        msg = f"unexpected output command: {command} in {cwd}"
        raise AssertionError(msg)

    original_config = (workdir / "schema" / "example" / "metaschema.yaml").read_text(
        encoding="utf-8"
    )
    original_gitmodules = (workdir / ".gitmodules").read_text(encoding="utf-8")

    summary = validate_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
        runner=runner,
        output_runner=output_runner,
    )

    submodule_dir = (workdir / "schema" / "submodules" / "vrs").resolve()

    assert summary.validated_only is True
    assert summary.submodules == [
        SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0")
    ]
    assert (workdir / "schema" / "example" / "metaschema.yaml").read_text(
        encoding="utf-8"
    ) == original_config
    assert (workdir / ".gitmodules").read_text(encoding="utf-8") == original_gitmodules
    assert commands == [
        (["git", "status", "--porcelain"], workdir.resolve()),
        (
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            workdir.resolve(),
        ),
        (
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            workdir.resolve(),
        ),
        (["git", "status", "--porcelain"], submodule_dir),
        (
            ["git", "rev-parse", "--verify", "origin/2.2.0-ballot^{commit}"],
            submodule_dir,
        ),
        (["git", "tag", "--merged", "origin/2.2.0-ballot"], submodule_dir),
        (["git", "rev-parse", "--verify", "v2.2.0^{commit}"], submodule_dir),
    ]


def test_prepare_release_matches_submodule_identifier_to_gitmodules_path_basename(
    tmp_path: Path,
) -> None:
    """Allow CLI identifiers like gks-core to match path submodules/gks-core."""
    workdir = _copy_release_fixture(tmp_path)
    gitmodules_fp = workdir / ".gitmodules"
    gitmodules_fp.write_text(
        """[submodule "schema/submodules/gks-core"]\n\tpath = schema/submodules/gks-core\n\turl = https://github.com/ga4gh/gks-core.git\n\tbranch = 1.1.0\n""",
        encoding="utf-8",
    )
    gks_core_dir = workdir / "schema" / "submodules" / "gks-core"
    gks_core_dir.mkdir(parents=True)
    commands: list[tuple[list[str], Path]] = []

    def runner(command: list[str], cwd: Path) -> None:
        """Record release commands instead of running git or make."""
        commands.append((command, cwd))
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[
            SubmoduleUpdate(
                identifier="gks-core", branch="1.2.0-ballot.2026-07", tag="v1.2.0"
            )
        ],
        runner=runner,
        output_runner=_clean_output,
    )

    assert "\tbranch = 1.2.0-ballot.2026-07" in gitmodules_fp.read_text(
        encoding="utf-8"
    )
    assert commands[0] == (
        [
            "git",
            "submodule",
            "update",
            "--remote",
            "--init",
            "--",
            "schema/submodules/gks-core",
        ],
        workdir.resolve(),
    )
    assert commands[1] == (["git", "fetch", "--all", "--tags"], gks_core_dir.resolve())


def test_prepare_release_rejects_unknown_submodule_identifier(tmp_path: Path) -> None:
    """Reject submodule identifiers that are not configured in .gitmodules."""
    workdir = _copy_release_fixture(tmp_path)

    with pytest.raises(
        ValueError,
        match=re.escape("Could not find a .gitmodules entry for submodule missing"),
    ):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="missing", branch="1.0.0-ballot")],
            output_runner=_clean_output,
        )


def test_prepare_release_rejects_multiple_submodule_updates(tmp_path: Path) -> None:
    """Reject release prep that tries to update more than one upstream product."""
    workdir = _copy_release_fixture(tmp_path)

    with pytest.raises(ValueError, match="one immediate upstream submodule"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[
                SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot"),
                SubmoduleUpdate(identifier="cat-vrs", branch="1.2.0-ballot"),
            ],
            output_runner=_clean_output,
        )


def test_prepare_release_rejects_missing_submodule_directory(tmp_path: Path) -> None:
    """Reject release prep when the configured submodule directory is absent."""
    workdir = _copy_release_fixture(tmp_path)
    shutil.rmtree(workdir / "schema" / "submodules" / "vrs")

    def runner(command: list[str], cwd: Path) -> None:
        """Do not create the missing submodule directory."""

    with pytest.raises(ValueError, match="does not exist after update"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
            runner=runner,
            output_runner=_clean_output,
        )


def test_prepare_release_rejects_missing_submodule_branch(tmp_path: Path) -> None:
    """Reject release prep when the requested submodule branch is not available."""
    workdir = _copy_release_fixture(tmp_path)

    def runner(command: list[str], cwd: Path) -> None:  # noqa: ARG001
        """Fail the git branch validation command."""
        if command == ["git", "rev-parse", "--verify", "origin/9.9.9-ballot^{commit}"]:
            raise subprocess.CalledProcessError(returncode=1, cmd=command)

    with pytest.raises(
        ValueError, match=re.escape("Could not find git branch origin/9.9.9-ballot")
    ):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="9.9.9-ballot")],
            runner=runner,
            output_runner=_clean_output,
        )


def test_prepare_release_rejects_missing_submodule_tag(tmp_path: Path) -> None:
    """Reject release prep when the requested submodule tag is not available."""
    workdir = _copy_release_fixture(tmp_path)

    def runner(command: list[str], cwd: Path) -> None:  # noqa: ARG001
        """Fail the git tag validation command."""
        if command == ["git", "rev-parse", "--verify", "v9.9.9^{commit}"]:
            raise subprocess.CalledProcessError(returncode=1, cmd=command)

    with pytest.raises(ValueError, match=re.escape("Could not find git tag v9.9.9")):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[
                SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v9.9.9")
            ],
            runner=runner,
            output_runner=_clean_output,
        )


def test_prepare_release_rejects_missing_latest_submodule_tag(tmp_path: Path) -> None:
    """Reject release prep when no latest reachable tag can be discovered."""
    workdir = _copy_release_fixture(tmp_path)

    def runner(command: list[str], cwd: Path) -> None:
        """Do not run git or make commands for this test."""

    def output_runner(command: list[str], cwd: Path) -> str:  # noqa: ARG001
        """Fail latest tag discovery."""
        if command == ["git", "status", "--porcelain"]:
            return ""
        raise subprocess.CalledProcessError(returncode=1, cmd=command)

    with pytest.raises(ValueError, match="Could not find a reachable git tag"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
            runner=runner,
            output_runner=output_runner,
        )


def test_prepare_release_rejects_missing_gitmodules_entry(tmp_path: Path) -> None:
    """Reject release prep when no .gitmodules entry matches the submodule."""
    workdir = _copy_release_fixture(tmp_path)
    (workdir / ".gitmodules").write_text(
        """[submodule "schema/submodules/other"]\n\tpath = schema/submodules/other\n\turl = https://example.org/other.git\n""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match=re.escape("Could not find a .gitmodules entry")
    ):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
            output_runner=_clean_output,
        )


def test_prepare_release_adds_missing_gitmodules_branch(tmp_path: Path) -> None:
    """Add a branch key when the matching .gitmodules entry does not have one."""
    workdir = _copy_release_fixture(tmp_path)
    gitmodules_fp = workdir / ".gitmodules"
    gitmodules_fp.write_text(
        """[submodule "schema/submodules/vrs"]\n\tpath = schema/submodules/vrs\n\turl = https://github.com/ga4gh/vrs.git\n""",
        encoding="utf-8",
    )

    def runner(command: list[str], cwd: Path) -> None:
        """Do not run git or make commands for this test."""
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[
            SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0")
        ],
        runner=runner,
        output_runner=_clean_output,
    )

    assert "\tbranch = 2.2.0-ballot" in gitmodules_fp.read_text(encoding="utf-8")


def test_main_infers_product_and_upstream_submodule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Infer the product and single upstream submodule from the repository."""
    workdir = _copy_release_fixture(tmp_path)
    repo_dir = tmp_path / "example"
    workdir.rename(repo_dir)
    calls: list[dict[str, object]] = []

    def prepare_stub(**kwargs: object) -> release_prep.ReleasePrepSummary:
        """Record the CLI arguments passed to release prep."""
        calls.append(kwargs)
        return release_prep.ReleasePrepSummary(
            product=str(kwargs["product"]),
            version=str(kwargs["version"]),
            product_dir=repo_dir / "schema" / "example",
            submodules=[],
        )

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(release_prep, "prepare_release", prepare_stub)

    assert (
        release_prep.main(["--version", "1.1.0", "--upstream-branch", "2.2.0-ballot"])
        == 0
    )
    assert calls[0]["product"] == "example"
    assert calls[0]["repo_dir"] == repo_dir.resolve()
    assert calls[0]["submodules"] == [
        SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")
    ]


def test_main_allows_product_without_upstream_submodule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Allow first-chain products such as gks-core to release without upstreams."""
    repo_dir = tmp_path / "gks-core"
    product_dir = repo_dir / "schema" / "gks-core"
    product_dir.mkdir(parents=True)
    (product_dir / "metaschema.yaml").write_text(
        "versions:\n  gks-core: 1.1.0\n", encoding="utf-8"
    )
    calls: list[dict[str, object]] = []

    def prepare_stub(**kwargs: object) -> release_prep.ReleasePrepSummary:
        """Record the CLI arguments passed to release prep."""
        calls.append(kwargs)
        return release_prep.ReleasePrepSummary(
            product=str(kwargs["product"]),
            version=str(kwargs["version"]),
            product_dir=product_dir,
            submodules=[],
        )

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(release_prep, "prepare_release", prepare_stub)

    assert release_prep.main(["--version", "1.2.0"]) == 0
    assert calls[0]["product"] == "gks-core"
    assert calls[0]["submodules"] is None


def test_main_rejects_submodules_directory_without_gitmodules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a submodule-looking checkout when .gitmodules is missing."""
    repo_dir = tmp_path / "example"
    product_dir = repo_dir / "schema" / "example"
    product_dir.mkdir(parents=True)
    (product_dir / "metaschema.yaml").write_text(
        "versions:\n  example: 1.0.0\n", encoding="utf-8"
    )
    (repo_dir / "schema" / "submodules").mkdir(parents=True)

    monkeypatch.chdir(repo_dir)

    with pytest.raises(
        ValueError, match=re.escape("Found submodules directory without .gitmodules")
    ):
        release_prep.main(["--version", "1.1.0"])


def test_main_requires_upstream_branch_when_submodule_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Require users to confirm the upstream branch for downstream products."""
    workdir = _copy_release_fixture(tmp_path)
    repo_dir = tmp_path / "example"
    workdir.rename(repo_dir)

    monkeypatch.chdir(repo_dir)

    with pytest.raises(
        ValueError,
        match="Provide --upstream-branch, --use-current-upstream-branch, or --skip-upstream",
    ):
        release_prep.main(["--version", "1.1.0"])


def test_main_can_skip_upstream_update_when_submodule_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow downstream releases to use the currently checked out upstream product."""
    workdir = _copy_release_fixture(tmp_path)
    repo_dir = tmp_path / "example"
    workdir.rename(repo_dir)
    calls: list[dict[str, object]] = []

    def prepare_stub(**kwargs: object) -> release_prep.ReleasePrepSummary:
        """Record the CLI arguments passed to release prep."""
        calls.append(kwargs)
        return release_prep.ReleasePrepSummary(
            product=str(kwargs["product"]),
            version=str(kwargs["version"]),
            product_dir=repo_dir / "schema" / "example",
            submodules=[],
        )

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(release_prep, "prepare_release", prepare_stub)

    assert release_prep.main(["--version", "1.1.0", "--skip-upstream"]) == 0
    assert calls[0]["submodules"] is None


def test_main_uses_current_upstream_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use the branch already configured in .gitmodules when explicitly confirmed."""
    workdir = _copy_release_fixture(tmp_path)
    repo_dir = tmp_path / "example"
    workdir.rename(repo_dir)
    calls: list[dict[str, object]] = []

    def prepare_stub(**kwargs: object) -> release_prep.ReleasePrepSummary:
        """Record the CLI arguments passed to release prep."""
        calls.append(kwargs)
        return release_prep.ReleasePrepSummary(
            product=str(kwargs["product"]),
            version=str(kwargs["version"]),
            product_dir=repo_dir / "schema" / "example",
            submodules=[],
        )

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(release_prep, "prepare_release", prepare_stub)

    assert (
        release_prep.main(["--version", "1.1.0", "--use-current-upstream-branch"]) == 0
    )
    assert calls[0]["submodules"] == [SubmoduleUpdate(identifier="vrs", branch="2.0.0")]


def test_main_uses_current_upstream_branch_with_explicit_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Allow an explicit tag while keeping the current .gitmodules branch."""
    workdir = _copy_release_fixture(tmp_path)
    repo_dir = tmp_path / "example"
    workdir.rename(repo_dir)
    calls: list[dict[str, object]] = []

    def prepare_stub(**kwargs: object) -> release_prep.ReleasePrepSummary:
        """Record the CLI arguments passed to release prep."""
        calls.append(kwargs)
        return release_prep.ReleasePrepSummary(
            product=str(kwargs["product"]),
            version=str(kwargs["version"]),
            product_dir=repo_dir / "schema" / "example",
            submodules=[],
        )

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(release_prep, "prepare_release", prepare_stub)

    assert (
        release_prep.main(
            [
                "--version",
                "1.1.0",
                "--use-current-upstream-branch",
                "--upstream-tag",
                "v2.1.0",
            ]
        )
        == 0
    )
    assert calls[0]["submodules"] == [
        SubmoduleUpdate(identifier="vrs", branch="2.0.0", tag="v2.1.0")
    ]


def test_main_rejects_conflicting_upstream_branch_options() -> None:
    """Reject CLI arguments that provide two upstream branch choices."""
    with pytest.raises(
        ValueError,
        match="Use either --upstream-branch or --use-current-upstream-branch",
    ):
        main(
            [
                "--version",
                "1.1.0",
                "--upstream-branch",
                "2.2.0-ballot",
                "--use-current-upstream-branch",
            ]
        )


def test_main_requires_upstream_branch_when_upstream_tag_is_provided() -> None:
    """Reject CLI arguments that provide a tag without an upstream branch."""
    with pytest.raises(
        ValueError,
        match="--upstream-tag requires --upstream-branch or --use-current-upstream-branch",
    ):
        main(
            [
                "--version",
                "1.1.0",
                "--upstream-tag",
                "v2.2.0",
            ]
        )


def test_main_rejects_skip_upstream_with_upstream_options() -> None:
    """Reject CLI arguments that both skip and configure upstream updates."""
    with pytest.raises(ValueError, match="Use --skip-upstream without"):
        main(
            [
                "--version",
                "1.1.0",
                "--skip-upstream",
                "--upstream-branch",
                "2.2.0-ballot",
            ]
        )


def test_main_rejects_multiple_inferred_upstream_submodules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject CLI inference when .gitmodules has more than one submodule."""
    workdir = _copy_release_fixture(tmp_path)
    repo_dir = tmp_path / "example"
    workdir.rename(repo_dir)
    (repo_dir / ".gitmodules").write_text(
        """[submodule "schema/submodules/vrs"]\n\tpath = schema/submodules/vrs\n[submodule "schema/submodules/cat-vrs"]\n\tpath = schema/submodules/cat-vrs\n""",
        encoding="utf-8",
    )

    monkeypatch.chdir(repo_dir)

    with pytest.raises(ValueError, match="expected one immediate upstream submodule"):
        release_prep.main(["--version", "1.1.0", "--upstream-branch", "2.2.0-ballot"])
