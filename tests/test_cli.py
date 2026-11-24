from anemone_kg.cli import PIPELINE, build_parser, ordered_stages


def test_run_all_follows_declared_pipeline_order():
    """Bug: stages registered in import order; isort made 'canonicalize' run before 'extract'."""
    build_parser()  # imports and registers the stages
    assert ordered_stages() == ["extract", "canonicalize", "resolve", "validate"]
    assert list(PIPELINE) == ordered_stages()
