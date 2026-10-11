"""An arXiv category is a subscription like the others.

The feature is one category per subscription row, for the reason the
bioRxiv subjects are: `discovered` is keyed
`UNIQUE(subscription_id, doi)`, so a row per category gives per-category
dedupe for nothing, and a paper cross-listed into two categories
appears under both rather than being collapsed into whichever was
fetched first. Cross-listing is information.

These tests cover the wiring between `arxiv.py` and the rest: the new
kind, the refresher arm, and the fact that an arXiv row must not cost
an Unpaywall lookup — at 472 announcements for `cs.LG` that would be
hundreds of requests per refresh to be told that a preprint is
readable, which the feed already said.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from alexandria import arxiv, feed, feed_window, index


@pytest.fixture
def conn(tmp_path):
    return index.open_db(str(tmp_path / "lib.db"))


# ---- the new kind ----------------------------------------------------

def test_a_category_can_be_followed(conn):
    sid = index.add_subscription(
        conn, "arxiv_category", arxiv.subscription_name("q-bio.BM"),
        "q-bio.BM")

    rows = list(index.list_subscriptions(conn))
    assert len(rows) == 1
    assert rows[0]["id"] == sid
    assert rows[0]["kind"] == "arxiv_category"
    assert rows[0]["query"] == "q-bio.BM"
    assert rows[0]["name"] == "arXiv q-bio.BM: Biomolecules"


def test_the_kind_check_still_refuses_nonsense(conn):
    with pytest.raises(ValueError):
        index.add_subscription(conn, "arxiv", "arXiv", "q-bio.BM")


def test_several_categories_are_several_subscriptions(conn):
    """One gesture in the picker, N rows - which is what gives each
    category its own dedupe scope."""
    for slug in ("q-bio.BM", "cond-mat.soft", "physics.bio-ph"):
        index.add_subscription(conn, "arxiv_category",
                               arxiv.subscription_name(slug), slug)

    kinds = [s["kind"] for s in index.list_subscriptions(conn)]
    assert kinds == ["arxiv_category"] * 3


def test_a_cross_listed_paper_lands_in_both_categories(conn):
    """The same DOI under two subscriptions is two rows, because the
    unique key includes the subscription."""
    a = index.add_subscription(conn, "arxiv_category",
                               arxiv.subscription_name("q-bio.BM"),
                               "q-bio.BM")
    b = index.add_subscription(conn, "arxiv_category",
                               arxiv.subscription_name("cond-mat.soft"),
                               "cond-mat.soft")
    paper = {"doi": "10.48550/arxiv.2510.00001", "title": "Crossed",
             "journal": "arXiv", "year": 2026}

    assert index.upsert_discovered(conn, a, paper)
    assert index.upsert_discovered(conn, b, paper)

    assert len(list(index.discovered_for(conn, a))) == 1
    assert len(list(index.discovered_for(conn, b))) == 1


def test_the_same_paper_twice_in_one_category_is_one_row(conn):
    """A `cross` announcement following a `new` one, say."""
    sid = index.add_subscription(conn, "arxiv_category",
                                 arxiv.subscription_name("q-bio.BM"),
                                 "q-bio.BM")
    paper = {"doi": "10.48550/arxiv.2510.00001", "title": "Once",
             "journal": "arXiv", "year": 2026}

    assert index.upsert_discovered(conn, sid, paper)
    assert not index.upsert_discovered(conn, sid, paper)

    assert len(list(index.discovered_for(conn, sid))) == 1


# ---- the refresher arm ----------------------------------------------

_ROW = {"doi": "10.48550/arxiv.2203.01250", "title": "A paper",
        "authors": ["Antonin Monteil"], "abstract": "Many works.",
        "journal": "arXiv", "year": 2024, "is_oa": True,
        "oa_status": "green",
        "oa_url": "https://arxiv.org/abs/2203.01250"}


def test_the_refresher_fetches_the_category(conn, monkeypatch):
    seen = {}

    def fake_fetch(category, **kw):
        seen["category"] = category
        return [_ROW]

    monkeypatch.setattr(arxiv, "fetch_category", fake_fetch)
    sid = index.add_subscription(conn, "arxiv_category", "arXiv q-bio.BM",
                                "q-bio.BM")
    sub = list(index.list_subscriptions(conn))[0]

    fetched, new = feed.refresh_subscription(conn, sub)

    assert seen["category"] == "q-bio.BM"
    assert (fetched, new) == (1, 1)
    assert len(list(index.discovered_for(conn, sid))) == 1


def test_an_arxiv_row_costs_no_unpaywall_lookup(conn, monkeypatch):
    """The feed already said the paper is readable, and pdf_fetch
    builds the URL from the DOI. For cs.LG this would be hundreds of
    requests per refresh."""
    from alexandria import metrics

    monkeypatch.setattr(arxiv, "fetch_category",
                        lambda category, **kw: [_ROW])

    def must_not_be_called(*a, **kw):
        raise AssertionError("Unpaywall was asked about an arXiv row")

    monkeypatch.setattr(metrics, "fetch_oa_locations", must_not_be_called)
    index.add_subscription(conn, "arxiv_category", "arXiv q-bio.BM",
                           "q-bio.BM")
    sub = list(index.list_subscriptions(conn))[0]

    assert feed.refresh_subscription(conn, sub) == (1, 1)


def test_an_empty_weekend_feed_is_a_successful_refresh(conn, monkeypatch):
    """Nothing fetched, nothing new, no exception - so the caller
    marks it fetched and does not retry in a loop."""
    monkeypatch.setattr(arxiv, "fetch_category", lambda category, **kw: [])
    index.add_subscription(conn, "arxiv_category", "arXiv q-bio.BM",
                           "q-bio.BM")
    sub = list(index.list_subscriptions(conn))[0]

    assert feed.refresh_subscription(conn, sub) == (0, 0)


# ---- the window ------------------------------------------------------

def test_the_feed_window_has_a_glyph_for_it():
    """Without one the row falls back to `[T]` and an arXiv standing
    order reads as a topic search."""
    assert feed_window._KIND_GLYPH["arxiv_category"] == "[P]"


def test_it_shares_the_preprint_glyph_with_biorxiv():
    """What the mark distinguishes is a preprint standing order from a
    journal or a topic; which server is in the subscription's name."""
    assert (feed_window._KIND_GLYPH["arxiv_category"]
            == feed_window._KIND_GLYPH["biorxiv_subject"])


def test_the_picker_offers_every_category():
    """The window builds its check buttons from `arxiv.CATEGORIES`, so
    a category added to the taxonomy appears without touching the UI.
    Asserted on the data rather than on widgets, which need a
    display."""
    from_groups = [slug for _, _, cats in arxiv.CATEGORIES
                   for slug, _label in cats]

    assert len(from_groups) == len(arxiv.ALL_CATEGORIES)
    assert set(from_groups) == set(arxiv.ALL_CATEGORIES)


def test_the_add_path_is_wired_to_the_arxiv_mode():
    import inspect

    src = inspect.getsource(feed_window.FeedWindow._on_add_query)

    assert '_add_mode == "arxiv"' in src
    assert "_do_add_arxiv_categories()" in src


def test_the_add_path_uses_the_new_kind():
    import inspect

    src = inspect.getsource(feed_window.FeedWindow._do_add_arxiv_categories)

    assert '"arxiv_category"' in src
    assert "arxiv.subscription_name" in src
