# GKS Metaschema Processor

The GKS metaschema processor (MSP) converts hand-edited GA4GH GKS source YAML
files into JSON Schema and reStructuredText artifacts. It is used by GKS-Core,
VRS, Cat-VRS, and VA-Spec.

MSP has two related responsibilities:

* Process source schemas, including imports, namespaces, class relationships,
  and generated JSON Schema and RST artifacts.
* Keep release versions consistent through one product-level
  `metaschema.yaml` configuration file and the local `gks-release-prep` command.

Schema authors normally use their product's `make all` workflow. Release users
run `gks-release-prep` for local release preparation. MSP is invoked through
those workflows rather than directly in most day-to-day use.

## Start Here

* Read [Architecture](architecture.md) to understand what MSP processes and
  what output it guarantees.
* Read [Metaschema Configuration](metaschema-config.md) before editing product
  source YAML or version metadata.
* Read [Release Preparation](release-prep.md) when preparing a local product
  release.
* See [Troubleshooting](troubleshooting.md) for common processing and release
  failures.

## Development

MSP supports Python 3.12. To prepare a local development environment:

```shell
git clone git@github.com:YOUR_GITHUB_ID/gks-metaschema.git
cd gks-metaschema
make devready
source venv/3.12/bin/activate
prek install
```

Run tests with `make test`. See [Contributing](contributing.md) for the project
workflow and coding expectations. Format and check code with:

```shell
python3 -m ruff format .
python3 -m ruff check .
```

To preview this documentation locally:

```shell
python3 -m pip install -e '.[docs]'
mkdocs serve
```
