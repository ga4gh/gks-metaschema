"""Release preparation and source-version management helpers.

Package modules:

- ``cli``: command parsing and release workflow orchestration.
- ``product_config``: product schema locations and ``metaschema.yaml`` edits.
- ``git``: immediate-upstream submodule metadata, validation, and checkout.
- ``worktree``: non-mutating Git worktree and branch-status checks.
- ``schema_versions``: source YAML version update and verification command.
- ``files``: atomic text-file writes for release-prep mutations.
"""

from ga4gh.gks.metaschema.tools.release_prep.cli import ReleasePrepSummary
from ga4gh.gks.metaschema.tools.release_prep.cli import cli as release_prep_cli
from ga4gh.gks.metaschema.tools.release_prep.cli import main as release_prep_main
from ga4gh.gks.metaschema.tools.release_prep.schema_versions import (
    cli as schema_versions_cli,
)
from ga4gh.gks.metaschema.tools.release_prep.schema_versions import (
    main as schema_versions_main,
)

__all__ = [
    "ReleasePrepSummary",
    "release_prep_cli",
    "release_prep_main",
    "schema_versions_cli",
    "schema_versions_main",
]
