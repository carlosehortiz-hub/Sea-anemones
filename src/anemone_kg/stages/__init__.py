"""Pipeline stages. Importing this package registers every stage with the CLI, in order."""

from anemone_kg.stages import build, canonicalize, extract, resolve, shacl, validate  # noqa: F401
