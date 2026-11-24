"""Pipeline stages. Importing this package registers every stage with the CLI, in order."""

from anemone_kg.stages import (  # noqa: F401
    build,
    canonicalize,
    extract,
    query,
    resolve,
    shacl,
    validate,
)
