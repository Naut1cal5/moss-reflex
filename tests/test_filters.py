import pytest

from moss_reflex.index import compile_filters


def test_compile_short_filters() -> None:
    assert compile_filters(
        {"$and": [{"repo": {"$eq": "abc"}}, {"outcome": {"$in": ["success", "resolved"]}}]}
    ) == {
        "$and": [
            {"field": "repo", "condition": {"$eq": "abc"}},
            {"field": "outcome", "condition": {"$in": ["success", "resolved"]}},
        ]
    }


@pytest.mark.parametrize(
    "value",
    [
        {"private": {"$eq": "x"}},
        {"repo": {"$ne": "x"}},
        {"repo": {"$in": "x"}},
        {"$and": []},
    ],
)
def test_rejects_unsupported_filters(value: dict) -> None:
    with pytest.raises(ValueError):
        compile_filters(value)
