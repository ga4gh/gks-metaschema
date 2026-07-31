"""Tests for end-to-end release-preparation workflows."""

from pathlib import Path

import yaml
from conftest import copy_release_prep_fixture, run_source_update, unexpected_command

from ga4gh.gks.metaschema.tools.release_prep.cli import (
    prepare_release,
    validate_release,
)
from ga4gh.gks.metaschema.tools.release_prep.git import (
    SubmoduleUpdate,
)


def _clean_output(command: list[str], cwd: Path) -> str:
    """Return clean git status output for tests that use explicit tags."""
    if command == ["git", "status", "--porcelain"]:
        return ""
    if command == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
        return "origin/main"
    if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
        return "0\t0"

    return unexpected_command(command, cwd)


def _run_fixture_make_all(command: list[str], cwd: Path, product_dir: Path) -> None:
    """Model the source update performed by the product ``make all`` target.

    :param command: Command passed to the fake runner.
    :param cwd: Command working directory.
    :param product_dir: Product schema directory to update.
    """
    if command != ["make", "all"]:
        return

    assert cwd == product_dir.parent.resolve()
    exit_code = run_source_update(product_dir.resolve())
    assert exit_code == 0


def test_prepare_release_updates_versions_and_runs_release_commands(
    tmp_path: Path,
) -> None:
    """Prepare a release and verify the expected workspace mutations and commands."""
    workdir = copy_release_prep_fixture(tmp_path)
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
        return unexpected_command(command, cwd)

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
        "Resolved submodule vrs tag v2.2.0",
        f"Updating {(workdir / 'schema' / 'example' / 'metaschema.yaml').resolve()} version example=1.1.0",
        "Updating source YAML version references",
        f"Running make clean in {(workdir / 'schema').resolve()}",
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
        (["git", "status", "--porcelain"], submodule_dir),
        (["git", "fetch", "--all", "--tags"], submodule_dir),
        (
            ["git", "rev-parse", "--verify", "origin/2.2.0-ballot^{commit}"],
            submodule_dir,
        ),
        (["git", "tag", "--merged", "origin/2.2.0-ballot"], submodule_dir),
        (["git", "rev-parse", "--verify", "v2.2.0^{commit}"], submodule_dir),
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
        (["git", "checkout", "v2.2.0"], submodule_dir),
        (["make", "clean"], (workdir / "schema").resolve()),
        (["make", "all"], (workdir / "schema").resolve()),
    ]


def test_prepare_release_uses_explicit_submodule_tag(tmp_path: Path) -> None:
    """Use an explicit tag instead of discovering the latest tag."""
    workdir = copy_release_prep_fixture(tmp_path)
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
        return unexpected_command(command, cwd)

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
        (["git", "fetch", "--all", "--tags"], submodule_dir),
        (
            ["git", "rev-parse", "--verify", "origin/2.2.0-ballot^{commit}"],
            submodule_dir,
        ),
        (
            ["git", "rev-parse", "--verify", "v2.2.0-ballot.2026-07.1^{commit}"],
            submodule_dir,
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
        (["git", "checkout", "v2.2.0-ballot.2026-07.1"], submodule_dir),
    ]


def test_validate_release_reports_values_without_mutating_files(tmp_path: Path) -> None:
    """Validate release inputs without updating files or running release commands."""
    workdir = copy_release_prep_fixture(tmp_path)
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
        return unexpected_command(command, cwd)

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
