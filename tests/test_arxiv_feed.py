"""arXiv category feeds.

Three things here are not guesses and are what the tests are about.

**Announcement types have four values, not three.** `new`, `cross`,
`replace` and `replace-cross` — the last is arXiv's own example in its
feed specification, and a filter written as `== "replace"` lets every
one of them through. They are papers the reader has already been
shown, and on 2026-10-09 replacements were between a third and a half
of every category sampled.

**The abstract and the announce type share the `description`.** It
opens `arXiv:2203.01250v3 Announce Type: replace-cross` and the
abstract follows `Abstract:`, so neither can be taken whole.

**The weekend feed is a valid channel with no items.** Verified
2026-10-11 on `q-bio.BM` and `cs.LG`: 200, `<skipDays>` naming
Saturday and Sunday, zero items. That must parse to an empty list
without looking like a fault, because a subscription is not dead just
because it is Sunday.

The item fixture follows the sample in arXiv's RSS specification,
since the feeds serve nothing at a weekend and this was written on
one.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from alexandria import arxiv


def _item(ident="2203.01250v3", announce="new", title="A paper",
          creator="Antonin Monteil, Paul Pegon",
          categories=("math.AP", "math.OC"),
          abstract="Many works have been devoted to the problem.",
          announce_element=True):
    bare = ident.split("v")[0]
    cats = "".join("  <category>{}</category>\n".format(c)
                   for c in categories)
    arxiv_el = ("  <arxiv:announce_type>{}</arxiv:announce_type>\n"
                .format(announce) if announce_element else "")
    return """ <item>
  <title>{title}</title>
  <link>https://arxiv.org/abs/{bare}</link>
  <description>arXiv:{ident} Announce Type: {announce}
Abstract: {abstract}</description>
  <guid isPermaLink="false">oai:arXiv.org:{ident}</guid>
{cats}  <pubDate>Fri, 23 Aug 2024 00:00:00 -0400</pubDate>
{arxiv_el}  <dc:creator>{creator}</dc:creator>
 </item>
""".format(title=title, bare=bare, ident=ident, announce=announce,
           abstract=abstract, cats=cats, arxiv_el=arxiv_el,
           creator=creator)


def _feed(*items):
    return ("""<?xml version='1.0' encoding='UTF-8'?>
<rss xmlns:arxiv="http://arxiv.org/schemas/atom"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:atom="http://www.w3.org/2005/Atom" version="2.0">
 <channel>
  <title>math.OC updates on arXiv.org</title>
  <link>http://rss.arxiv.org/rss/math.OC</link>
  <lastBuildDate>Fri, 23 Feb 2024 05:00:11 +0000</lastBuildDate>
  <skipDays><day>Saturday</day><day>Sunday</day></skipDays>
""" + "".join(items) + """ </channel>
</rss>
""").encode("utf-8")


# ---- the taxonomy ----------------------------------------------------

def test_every_archive_has_categories():
    assert len(arxiv.CATEGORIES) == 8
    for slug, label, cats in arxiv.CATEGORIES:
        assert slug and label and cats


def test_the_whole_taxonomy_is_there():
    """155 as taken from arxiv.org/category_taxonomy on 2026-10-11.
    A drop would mean a parse of that page had silently lost a group."""
    assert len(arxiv.ALL_CATEGORIES) == 155
    assert len(set(arxiv.ALL_CATEGORIES)) == 155, "a slug appears twice"


def test_the_archives_that_open_by_default_exist():
    groups = {slug for slug, _, _ in arxiv.CATEGORIES}
    assert set(arxiv.DEFAULT_OPEN) <= groups


@pytest.mark.parametrize("slug,label", [
    ("q-bio.BM", "Biomolecules"),
    ("cond-mat.soft", "Soft Condensed Matter"),
    ("cs.LG", "Machine Learning"),
])
def test_labels_come_from_the_taxonomy(slug, label):
    assert arxiv.category_label(slug) == label


def test_an_unknown_category_is_its_own_label():
    """arXiv adds categories; an unlabelled one must still be
    displayable rather than blank."""
    assert arxiv.category_label("q-bio.ZZ") == "q-bio.ZZ"


def test_the_subscription_name_carries_slug_and_label():
    assert arxiv.subscription_name("q-bio.BM") == (
        "arXiv q-bio.BM: Biomolecules")


def test_the_feed_url_is_the_category():
    assert arxiv.feed_url("q-bio.BM") == (
        "https://rss.arxiv.org/rss/q-bio.BM")


# ---- identifiers and DOIs -------------------------------------------

@pytest.mark.parametrize("link,expected", [
    ("https://arxiv.org/abs/2203.01250", "2203.01250"),
    ("https://arxiv.org/abs/2203.01250v3", "2203.01250"),
    ("https://arxiv.org/abs/math/0309136", "math/0309136"),
])
def test_the_identifier_comes_out_of_the_link(link, expected):
    assert arxiv.arxiv_id(link) == expected


def test_the_guid_will_do_if_the_link_is_missing():
    assert arxiv.arxiv_id(None, "oai:arXiv.org:2203.01250v3") == (
        "2203.01250")


def test_the_version_is_dropped():
    """It belongs to the announcement, not the paper, and the DOI
    arXiv mints has no version in it."""
    assert arxiv.arxiv_id("https://arxiv.org/abs/2510.09999v7") == (
        "2510.09999")


def test_the_doi_is_the_one_extract_already_knows():
    """A downloaded arXiv PDF is identified from its filename by
    `extract.doi_from_filename`, which produces this same string. The
    two must agree, or the same paper arriving by the two routes would
    occupy two rows."""
    from alexandria import extract

    assert arxiv.doi_for("2006.11239") == "10.48550/arxiv.2006.11239"
    assert extract.doi_from_filename("2006.11239v2.pdf") == (
        arxiv.doi_for("2006.11239"))


def test_no_identifier_means_no_doi():
    assert arxiv.doi_for(None) is None


# ---- the announcement filter ----------------------------------------

@pytest.mark.parametrize("announce,replacement", [
    ("new", False),
    ("cross", False),
    ("replace", True),
    ("replace-cross", True),
])
def test_replacements_are_recognised_by_prefix(announce, replacement):
    assert arxiv.is_replacement(announce) is replacement


def test_a_replacement_is_left_out():
    rows = arxiv.parse_feed(_feed(_item(announce="replace")))

    assert rows == []


def test_a_replaced_cross_listing_is_left_out_too():
    """The case `== "replace"` would miss, and arXiv's own
    specification uses it as its example."""
    rows = arxiv.parse_feed(_feed(_item(announce="replace-cross")))

    assert rows == []


def test_a_cross_listing_is_kept():
    """A paper surfacing in a second category is information - the
    ruling already made for bioRxiv subjects."""
    rows = arxiv.parse_feed(_feed(_item(announce="cross")))

    assert len(rows) == 1


def test_replacements_can_be_asked_for():
    rows = arxiv.parse_feed(_feed(_item(announce="replace")),
                            keep_replacements=True)

    assert len(rows) == 1


def test_the_announce_type_is_read_from_the_description_if_it_has_to_be():
    """The whole filter turns on this one value, so it is worth not
    depending on a single element."""
    rows = arxiv.parse_feed(
        _feed(_item(announce="replace", announce_element=False)))

    assert rows == []


def test_a_mixed_feed_keeps_only_what_is_new():
    rows = arxiv.parse_feed(_feed(
        _item(ident="2510.00001v1", announce="new", title="New one"),
        _item(ident="2203.01250v3", announce="replace", title="Old one"),
        _item(ident="2510.00002v1", announce="cross", title="Crossed"),
        _item(ident="2109.00003v2", announce="replace-cross",
              title="Old and crossed"),
    ))

    assert [r["title"] for r in rows] == ["New one", "Crossed"]


# ---- the row ---------------------------------------------------------

def test_a_row_is_complete_from_the_feed_alone():
    """No enrichment call: that is the whole bargain of using RSS."""
    rows = arxiv.parse_feed(_feed(_item()))

    assert len(rows) == 1
    row = rows[0]
    assert row["doi"] == "10.48550/arxiv.2203.01250"
    assert row["title"] == "A paper"
    assert row["authors"] == ["Antonin Monteil", "Paul Pegon"]
    assert row["abstract"] == "Many works have been devoted to the problem."
    assert row["journal"] == "arXiv"
    assert row["year"] == 2024
    assert row["is_oa"] is True
    assert row["oa_status"] == "green"
    assert row["oa_url"] == "https://arxiv.org/abs/2203.01250"
    assert row["categories"] == ["math.AP", "math.OC"]
    assert row["announce_type"] == "new"


def test_the_identifier_line_is_not_part_of_the_abstract():
    rows = arxiv.parse_feed(_feed(_item()))

    assert "Announce Type" not in rows[0]["abstract"]
    assert "arXiv:2203" not in rows[0]["abstract"]


def test_a_long_abstract_survives_whole():
    """1,100 to 1,900 characters in the 2026-10-09 sample, and the
    point of the feed is that they arrive complete."""
    long_one = "Sentence number one. " * 90
    rows = arxiv.parse_feed(_feed(_item(abstract=long_one)))

    assert len(rows[0]["abstract"]) > 1100


def test_authors_are_already_in_reading_order():
    """Unlike bioRxiv's "Surname, Initials", so no reassembly."""
    rows = arxiv.parse_feed(
        _feed(_item(creator="Paul Emsley, Kevin Cowtan")))

    assert rows[0]["authors"] == ["Paul Emsley", "Kevin Cowtan"]


def test_an_item_with_no_identifier_is_skipped():
    """`discovered` is keyed on the DOI, so a row without one has no
    dedupe key and cannot be stored."""
    broken = _item().replace(
        "<link>https://arxiv.org/abs/2203.01250</link>", "<link/>"
    ).replace('<guid isPermaLink="false">oai:arXiv.org:2203.01250v3</guid>',
              "<guid/>")

    assert arxiv.parse_feed(_feed(broken)) == []


# ---- the weekend -----------------------------------------------------

def test_a_weekend_feed_is_empty_not_broken():
    """Measured 2026-10-11, a Sunday: 200, a valid channel, no items.
    This must not read as a failure."""
    rows = arxiv.parse_feed(_feed())

    assert rows == []


def test_rubbish_is_empty_too():
    assert arxiv.parse_feed(b"<not xml") == []
    assert arxiv.parse_feed(b"") == []


# ---- fetching --------------------------------------------------------

def test_fetch_passes_the_category_to_the_feed():
    seen = {}

    def fake_get(url, timeout=30):
        seen["url"] = url
        return _feed(_item())

    rows = arxiv.fetch_category("q-bio.BM", http_get=fake_get)

    assert seen["url"] == "https://rss.arxiv.org/rss/q-bio.BM"
    assert len(rows) == 1


def test_a_failed_fetch_is_empty_and_does_not_raise():
    """The refresher loop handles an empty list anyway, since that is
    also the honest weekend answer."""

    def boom(url, timeout=30):
        raise OSError("no route to host")

    assert arxiv.fetch_category("q-bio.BM", http_get=boom) == []
