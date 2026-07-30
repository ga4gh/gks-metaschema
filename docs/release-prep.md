# Release Prep

`gks-release-prep` automates the local steps used to prepare a GKS product
release from `metaschema.yaml`.

Run this command from the root of the product repository being released. The
repository root must contain `schema/`. The product name is inferred from the
repository directory name; for example, a checkout directory named `va-spec`
uses `schema/va-spec/metaschema.yaml`.

## What It Automates

Before release prep was automated, release users had to do the following
manually:

* update the immediate upstream submodule branch in `.gitmodules`
* initialize the upstream submodule if needed
* update the upstream submodule from the configured remote branch
* choose and check out the upstream release tag
* update the local product version in `schema/<product>/metaschema.yaml`
* update source YAML version references before build validation runs
* run `make all`, which updates source YAML version references and regenerates artifacts
* run `source2updated --check --disallow-versioned-refs`

The command performs those steps locally. It does not stage files, commit, tag,
or push changes. Review the working tree diff and create the release commit
manually.

Release prep warns if the product repo or upstream submodule has uncommitted
changes. Use `--fail-on-dirty` when those warnings should fail the command
instead. For downstream products, it also prints a warning if the product branch
has no upstream tracking branch, is behind upstream, is ahead of upstream, or
has diverged.

## Downstream Products

For downstream products, the immediate upstream product is inferred from the
single submodule entry in `.gitmodules`. Release prep intentionally accepts only
one immediate upstream submodule. Transitive upstream products should be updated
in their own release branches first.

Provide `--upstream-branch` when the upstream branch should be changed or
explicitly rewritten:

```shell
gks-release-prep --version 1.1.0 --upstream-branch 1.2.0-ballot.2026-07
```

If the existing `.gitmodules` branch is already correct, provide
`--use-current-upstream-branch` instead:

```shell
gks-release-prep --version 1.1.0 --use-current-upstream-branch
```

In both cases, release prep initializes the submodule if needed, fetches remote
branches and tags, verifies `origin/<branch>`, updates the submodule from that
remote branch, checks out the highest semantic-version tag reachable from it,
updates the local product version, updates source YAML version references, runs
`make all`, and finishes by verifying source YAML references with
`source2updated --check`.

To pin a specific upstream tag instead of using the latest reachable tag, pass
`--upstream-tag`:

```shell
gks-release-prep --version 1.1.0 --upstream-branch 1.2.0-ballot.2026-07 --upstream-tag v1.2.0-ballot.2026-07.1
```

If the current `.gitmodules` branch is correct and only the tag should be
pinned, combine the tag with `--use-current-upstream-branch`.

If the imported product is already at the correct checkout and should not be
updated, use `--skip-upstream`:

```shell
gks-release-prep --version 1.1.0 --skip-upstream
```

This leaves `.gitmodules` and the submodule checkout unchanged, then updates the
local product version, updates source YAML version references, runs `make all`,
and verifies source YAML references.

## First Product

The first product in the release chain, such as `gks-core`, has no upstream
submodule. For those products, omit the upstream flags:

```shell
gks-release-prep --version 1.2.0
```

If `.gitmodules` is missing but a `submodules` directory exists, release prep
fails because the checkout looks like a downstream product with incomplete
submodule metadata.

## Validation

To validate the product config, `.gitmodules` entry, submodule directory,
branch, and resolved tag without changing files, add `--validate`:

```shell
gks-release-prep --validate --version 1.1.0 --upstream-branch 1.2.0-ballot.2026-07
```

The command prints the product, schema path, submodule branch/tag, and build
steps as it runs.

Validation checks the local git state only. It does not initialize submodules,
fetch tags, update remote branches, or change files.
