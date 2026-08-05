"""Tests for release-prep command-line argument handling."""

from pathlib import Path

import pytest
from conftest import copy_release_prep_fixture

from ga4gh.gks.metaschema.tools.release_prep import cli as release_prep
from ga4gh.gks.metaschema.tools.release_prep.cli import main
from ga4gh.gks.metaschema.tools.release_prep.git import SubmoduleUpdate


def test_main_infers_product_and_upstream_submodule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Infer the product and single upstream submodule from the repository."""
    workdir = copy_release_prep_fixture(tmp_path)
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

    assert release_prep.main(["--version", "1.1.0", "--upstream-branch", "2.2.0-ballot"]) == 0
    assert calls[0]["product"] == "example"
    assert calls[0]["repo_dir"] == repo_dir.resolve()
    assert calls[0]["submodules"] == [SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")]


def test_main_allows_product_without_upstream_submodule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow first-chain products such as gks-core to release without upstreams."""
    repo_dir = tmp_path / "gks-core"
    product_dir = repo_dir / "schema" / "gks-core"
    product_dir.mkdir(parents=True)
    (product_dir / "metaschema.yaml").write_text("versions:\n  gks-core: 1.1.0\n", encoding="utf-8")
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


def test_main_rejects_submodules_directory_without_gitmodules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject a submodule-looking checkout when .gitmodules is missing."""
    repo_dir = tmp_path / "example"
    product_dir = repo_dir / "schema" / "example"
    product_dir.mkdir(parents=True)
    (product_dir / "metaschema.yaml").write_text("versions:\n  example: 1.0.0\n", encoding="utf-8")
    (repo_dir / "schema" / "submodules").mkdir(parents=True)

    monkeypatch.chdir(repo_dir)

    with pytest.raises(ValueError, match="Found submodules directory without .gitmodules"):
        release_prep.main(["--version", "1.1.0"])


def test_main_requires_upstream_branch_when_submodule_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Require users to confirm the upstream branch for downstream products."""
    workdir = copy_release_prep_fixture(tmp_path)
    repo_dir = tmp_path / "example"
    workdir.rename(repo_dir)

    monkeypatch.chdir(repo_dir)

    with pytest.raises(
        ValueError, match="Provide --upstream-branch, --use-current-upstream-branch, or --skip-upstream"
    ):
        release_prep.main(["--version", "1.1.0"])


def test_main_can_skip_upstream_update_when_submodule_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow downstream releases to use the currently checked out upstream product."""
    workdir = copy_release_prep_fixture(tmp_path)
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


def test_main_uses_current_upstream_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the branch already configured in .gitmodules when explicitly confirmed."""
    workdir = copy_release_prep_fixture(tmp_path)
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

    assert release_prep.main(["--version", "1.1.0", "--use-current-upstream-branch"]) == 0
    assert calls[0]["submodules"] == [SubmoduleUpdate(identifier="vrs", branch="2.0.0")]


def test_main_uses_current_upstream_branch_with_explicit_tag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow an explicit tag while keeping the current .gitmodules branch."""
    workdir = copy_release_prep_fixture(tmp_path)
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

    assert release_prep.main(["--version", "1.1.0", "--use-current-upstream-branch", "--upstream-tag", "v2.1.0"]) == 0
    assert calls[0]["submodules"] == [SubmoduleUpdate(identifier="vrs", branch="2.0.0", tag="v2.1.0")]


def test_main_rejects_conflicting_upstream_branch_options() -> None:
    """Reject CLI arguments that provide two upstream branch choices."""
    with pytest.raises(ValueError, match="Use either --upstream-branch or --use-current-upstream-branch"):
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
    with pytest.raises(ValueError, match="--upstream-tag requires --upstream-branch or --use-current-upstream-branch"):
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


def test_main_rejects_multiple_inferred_upstream_submodules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject CLI inference when .gitmodules has more than one submodule."""
    workdir = copy_release_prep_fixture(tmp_path)
    repo_dir = tmp_path / "example"
    workdir.rename(repo_dir)
    (repo_dir / ".gitmodules").write_text(
        """[submodule "schema/submodules/vrs"]\n\tpath = schema/submodules/vrs\n[submodule "schema/submodules/cat-vrs"]\n\tpath = schema/submodules/cat-vrs\n""",
        encoding="utf-8",
    )

    monkeypatch.chdir(repo_dir)

    with pytest.raises(ValueError, match="expected one immediate upstream submodule"):
        release_prep.main(["--version", "1.1.0", "--upstream-branch", "2.2.0-ballot"])
