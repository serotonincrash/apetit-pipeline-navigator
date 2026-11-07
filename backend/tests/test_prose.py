"""The prose check finds each banned pattern and leaves plain text and tokens alone."""

import pytest

from navigator.prose import check


def test_plain_text_passes() -> None:
    assert check("Drops parcels with no area, so the totals match the farm registry.") == []


@pytest.mark.parametrize(
    "text",
    [
        "The step runs fast — and drops rows.",
        "Yield is 3 \u00d7 higher.",
        "Moves rows → clean table.",
        "Area ≠ declared area.",
        "At least ≥ 5 parcels.",
        "Up to ≤ 5 parcels.",
        "About ~5 parcels.",
        "Robust checks on the farm file.",
        "This will Leverage the data.",
        "Gives actionable findings for each crop.",
        "Covers various crops.",
        "Handles a number of farms.",
        "Drops rows and more.",
        "Done!",
        "The fix is not a guess but a rule.",
        "It's not just a check, it's a policy.",
    ],
)
def test_each_banned_pattern_is_found(text: str) -> None:
    assert check(text) != []


def test_banned_words_match_whole_words_only() -> None:
    assert check("The landscaper checked the ensured rows.") == []
    assert check("Parcels sit in a landscape.") != []


def test_tilde_without_a_number_is_fine() -> None:
    assert check("Files end in ~ backups.") == []


def test_tokens_are_not_checked() -> None:
    assert check("Costs {{metric:a — b ~5 robust}} a year.") == []


def test_word_limit() -> None:
    assert check("one two three", max_words=3) == []
    problems = check("one two three four", max_words=3)
    assert problems == ["Has 4 words, over the limit of 3."]


def test_insight_is_a_domain_term_not_a_banned_word() -> None:
    assert check("A dashboard of its key metrics and insights.") == []
