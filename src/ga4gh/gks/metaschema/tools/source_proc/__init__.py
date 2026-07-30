"""Process GKS source YAML into resolved schema artifacts.

Package layout:

- ``processor``: ``YamlSchemaProcessor`` state and the small public API used by
  scripts and tests.
- ``config``: applies ``metaschema.yaml`` configuration to one source schema.
- ``imports``: loads imported source schemas and merges them when requested.
- ``graph``: class lookup, inheritance/container graph building, and class
  relationship queries.
- ``paths``: CURIE resolution, local ``$ref`` rewriting, and generated artifact
  path helpers.
- ``classes``: class-level processing flow.
- ``properties``: property extension and property validation rules.
- ``output``: cleanup for generated JSON Schema output.

Terms used in this package:

- ``raw schema``: parsed source YAML before MSP processing.
- ``processed schema``: schema after imports, inheritance, and validation rules
  have been applied.
- ``for_js``: processed schema copy prepared for JSON Schema and split artifact
  output.
"""

from ga4gh.gks.metaschema.tools.source_proc.processor import YamlSchemaProcessor

__all__ = ["YamlSchemaProcessor"]
