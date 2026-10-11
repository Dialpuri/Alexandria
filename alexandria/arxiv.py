"""arXiv category feeds.

The standing-order half of arXiv, in the same shape as `biorxiv`: one
RSS feed per category, so a subscription is a *category* and you take
what arrives. There is deliberately no search here.

**Why not the search API.** `export.arxiv.org/api/query` answered 429
"Rate exceeded" on every attempt on 2026-10-09, with a correct
descriptive User-Agent, and then stopped answering at all while
`arxiv.org/abs/` and the RSS host kept serving 200s from the same
machine. It had worked earlier in the project from another machine, so
this is rate limiting or address reputation rather than a block — which
is the point: anything that needs that endpoint on a keystroke is
fragile by construction, and fails worst for the user behind a shared
institutional address. The feeds answered 200 throughout.

**What the feed gives.** RSS 2.0 (not bioRxiv's RDF), and a row is
complete from the feed alone, with no enrichment call: title,
`dc:creator`, the `abs` link, every `category`, `pubDate`, and the
whole abstract inside `description` (1,100-1,900 characters in the
2026-10-09 sample).

**Weekdays only, and it says so.** The channel carries
`<skipDays><day>Saturday</day><day>Sunday</day></skipDays>`, and at a
weekend the feed is a valid channel with no items at all — verified
2026-10-11, a Sunday, on `q-bio.BM` and `cs.LG`. So an empty feed is
the correct answer rather than a fault, and must not mark a
subscription dead. arXiv announces once per weekday and the feed holds
one cycle, so an announcement missed is missed for good.

**`arxiv:announce_type` has to be read, and it has four values, not
three.** Besides `new`, `cross` and `replace` there is `replace-cross`
(arXiv's own documented example is one), so the filter tests the
prefix rather than equality — `replace` means a paper already seen
being re-announced, and often half a feed is replacements. Cross
listings are kept: a paper appearing in two sections is information,
which is the ruling already applied to bioRxiv subjects.

**Volume differs between categories by two orders of magnitude.**
Measured 2026-10-09: `q-bio.BM` 6 items, `physics.bio-ph` 9,
`cond-mat.soft` 14, `math.NA` 50, `cs.LG` 472. The feed window already
copes, having been grouped per subscription for the 27 bioRxiv
subjects (`feed_window._PER_GROUP_CAP`), but the `discovered` table
takes all of them.

The item shape below follows arXiv's published RSS specification. The
2026-10-09 measurements were made on the other machine; parsing here
was written against the specification's own sample and the fixture in
`tests/test_arxiv_feed.py` is modelled on it, so the first weekday
fetch is worth watching.
"""

import re
import xml.etree.ElementTree as ET
import urllib.request

from .identity import user_agent

FEED_URL = "https://rss.arxiv.org/rss/"

_DC = "{http://purl.org/dc/elements/1.1/}"
_ARXIV = "{http://arxiv.org/schemas/atom}"

# The archives that open without being asked. The project's readers
# are structural biologists first, and these two hold the categories
# they would look for; the rest are one click away. Widening past
# biology is the whole reason arXiv is here, so nothing is omitted.
DEFAULT_OPEN = ("q-bio", "physics")

CATEGORIES = (
    ("q-bio", "Quantitative Biology", (
        ("q-bio.BM", "Biomolecules"),
        ("q-bio.CB", "Cell Behavior"),
        ("q-bio.GN", "Genomics"),
        ("q-bio.MN", "Molecular Networks"),
        ("q-bio.NC", "Neurons and Cognition"),
        ("q-bio.OT", "Other Quantitative Biology"),
        ("q-bio.PE", "Populations and Evolution"),
        ("q-bio.QM", "Quantitative Methods"),
        ("q-bio.SC", "Subcellular Processes"),
        ("q-bio.TO", "Tissues and Organs"),
    )),
    ("physics", "Physics", (
        ("astro-ph.CO", "Cosmology and Nongalactic Astrophysics"),
        ("astro-ph.EP", "Earth and Planetary Astrophysics"),
        ("astro-ph.GA", "Astrophysics of Galaxies"),
        ("astro-ph.HE", "High Energy Astrophysical Phenomena"),
        ("astro-ph.IM", "Instrumentation and Methods for Astrophysics"),
        ("astro-ph.SR", "Solar and Stellar Astrophysics"),
        ("cond-mat.dis-nn", "Disordered Systems and Neural Networks"),
        ("cond-mat.mes-hall", "Mesoscale and Nanoscale Physics"),
        ("cond-mat.mtrl-sci", "Materials Science"),
        ("cond-mat.other", "Other Condensed Matter"),
        ("cond-mat.quant-gas", "Quantum Gases"),
        ("cond-mat.soft", "Soft Condensed Matter"),
        ("cond-mat.stat-mech", "Statistical Mechanics"),
        ("cond-mat.str-el", "Strongly Correlated Electrons"),
        ("cond-mat.supr-con", "Superconductivity"),
        ("gr-qc", "General Relativity and Quantum Cosmology"),
        ("hep-ex", "High Energy Physics - Experiment"),
        ("hep-lat", "High Energy Physics - Lattice"),
        ("hep-ph", "High Energy Physics - Phenomenology"),
        ("hep-th", "High Energy Physics - Theory"),
        ("math-ph", "Mathematical Physics"),
        ("nlin.AO", "Adaptation and Self-Organizing Systems"),
        ("nlin.CD", "Chaotic Dynamics"),
        ("nlin.CG", "Cellular Automata and Lattice Gases"),
        ("nlin.PS", "Pattern Formation and Solitons"),
        ("nlin.SI", "Exactly Solvable and Integrable Systems"),
        ("nucl-ex", "Nuclear Experiment"),
        ("nucl-th", "Nuclear Theory"),
        ("physics.acc-ph", "Accelerator Physics"),
        ("physics.ao-ph", "Atmospheric and Oceanic Physics"),
        ("physics.app-ph", "Applied Physics"),
        ("physics.atm-clus", "Atomic and Molecular Clusters"),
        ("physics.atom-ph", "Atomic Physics"),
        ("physics.bio-ph", "Biological Physics"),
        ("physics.chem-ph", "Chemical Physics"),
        ("physics.class-ph", "Classical Physics"),
        ("physics.comp-ph", "Computational Physics"),
        ("physics.data-an", "Data Analysis, Statistics and Probability"),
        ("physics.ed-ph", "Physics Education"),
        ("physics.flu-dyn", "Fluid Dynamics"),
        ("physics.gen-ph", "General Physics"),
        ("physics.geo-ph", "Geophysics"),
        ("physics.hist-ph", "History and Philosophy of Physics"),
        ("physics.ins-det", "Instrumentation and Detectors"),
        ("physics.med-ph", "Medical Physics"),
        ("physics.optics", "Optics"),
        ("physics.plasm-ph", "Plasma Physics"),
        ("physics.pop-ph", "Popular Physics"),
        ("physics.soc-ph", "Physics and Society"),
        ("physics.space-ph", "Space Physics"),
        ("quant-ph", "Quantum Physics"),
    )),
    ("cs", "Computer Science", (
        ("cs.AI", "Artificial Intelligence"),
        ("cs.AR", "Hardware Architecture"),
        ("cs.CC", "Computational Complexity"),
        ("cs.CE", "Computational Engineering, Finance, and Science"),
        ("cs.CG", "Computational Geometry"),
        ("cs.CL", "Computation and Language"),
        ("cs.CR", "Cryptography and Security"),
        ("cs.CV", "Computer Vision and Pattern Recognition"),
        ("cs.CY", "Computers and Society"),
        ("cs.DB", "Databases"),
        ("cs.DC", "Distributed, Parallel, and Cluster Computing"),
        ("cs.DL", "Digital Libraries"),
        ("cs.DM", "Discrete Mathematics"),
        ("cs.DS", "Data Structures and Algorithms"),
        ("cs.ET", "Emerging Technologies"),
        ("cs.FL", "Formal Languages and Automata Theory"),
        ("cs.GL", "General Literature"),
        ("cs.GR", "Graphics"),
        ("cs.GT", "Computer Science and Game Theory"),
        ("cs.HC", "Human-Computer Interaction"),
        ("cs.IR", "Information Retrieval"),
        ("cs.IT", "Information Theory"),
        ("cs.LG", "Machine Learning"),
        ("cs.LO", "Logic in Computer Science"),
        ("cs.MA", "Multiagent Systems"),
        ("cs.MM", "Multimedia"),
        ("cs.MS", "Mathematical Software"),
        ("cs.NA", "Numerical Analysis"),
        ("cs.NE", "Neural and Evolutionary Computing"),
        ("cs.NI", "Networking and Internet Architecture"),
        ("cs.OH", "Other Computer Science"),
        ("cs.OS", "Operating Systems"),
        ("cs.PF", "Performance"),
        ("cs.PL", "Programming Languages"),
        ("cs.RO", "Robotics"),
        ("cs.SC", "Symbolic Computation"),
        ("cs.SD", "Sound"),
        ("cs.SE", "Software Engineering"),
        ("cs.SI", "Social and Information Networks"),
        ("cs.SY", "Systems and Control"),
    )),
    ("eess", "Electrical Engineering and Systems Science", (
        ("eess.AS", "Audio and Speech Processing"),
        ("eess.IV", "Image and Video Processing"),
        ("eess.SP", "Signal Processing"),
        ("eess.SY", "Systems and Control"),
    )),
    ("math", "Mathematics", (
        ("math.AC", "Commutative Algebra"),
        ("math.AG", "Algebraic Geometry"),
        ("math.AP", "Analysis of PDEs"),
        ("math.AT", "Algebraic Topology"),
        ("math.CA", "Classical Analysis and ODEs"),
        ("math.CO", "Combinatorics"),
        ("math.CT", "Category Theory"),
        ("math.CV", "Complex Variables"),
        ("math.DG", "Differential Geometry"),
        ("math.DS", "Dynamical Systems"),
        ("math.FA", "Functional Analysis"),
        ("math.GM", "General Mathematics"),
        ("math.GN", "General Topology"),
        ("math.GR", "Group Theory"),
        ("math.GT", "Geometric Topology"),
        ("math.HO", "History and Overview"),
        ("math.IT", "Information Theory"),
        ("math.KT", "K-Theory and Homology"),
        ("math.LO", "Logic"),
        ("math.MG", "Metric Geometry"),
        ("math.MP", "Mathematical Physics"),
        ("math.NA", "Numerical Analysis"),
        ("math.NT", "Number Theory"),
        ("math.OA", "Operator Algebras"),
        ("math.OC", "Optimization and Control"),
        ("math.PR", "Probability"),
        ("math.QA", "Quantum Algebra"),
        ("math.RA", "Rings and Algebras"),
        ("math.RT", "Representation Theory"),
        ("math.SG", "Symplectic Geometry"),
        ("math.SP", "Spectral Theory"),
        ("math.ST", "Statistics Theory"),
    )),
    ("stat", "Statistics", (
        ("stat.AP", "Applications"),
        ("stat.CO", "Computation"),
        ("stat.ME", "Methodology"),
        ("stat.ML", "Machine Learning"),
        ("stat.OT", "Other Statistics"),
        ("stat.TH", "Statistics Theory"),
    )),
    ("econ", "Economics", (
        ("econ.EM", "Econometrics"),
        ("econ.GN", "General Economics"),
        ("econ.TH", "Theoretical Economics"),
    )),
    ("q-fin", "Quantitative Finance", (
        ("q-fin.CP", "Computational Finance"),
        ("q-fin.EC", "Economics"),
        ("q-fin.GN", "General Finance"),
        ("q-fin.MF", "Mathematical Finance"),
        ("q-fin.PM", "Portfolio Management"),
        ("q-fin.PR", "Pricing of Securities"),
        ("q-fin.RM", "Risk Management"),
        ("q-fin.ST", "Statistical Finance"),
        ("q-fin.TR", "Trading and Market Microstructure"),
    )),
)


# Flat lookups built from the taxonomy above, so the UI can group and
# the feed refresher can validate without walking it each time.
CATEGORY_LABELS = {slug: label
                   for _, _, cats in CATEGORIES
                   for slug, label in cats}
ALL_CATEGORIES = tuple(CATEGORY_LABELS)


def category_label(slug):
    """`"q-bio.BM"` → `"Biomolecules"`, and the slug itself for a
    category arXiv has added since this list was taken."""
    return CATEGORY_LABELS.get(slug) or slug


def subscription_name(slug):
    """What the subscription row is called: `"arXiv q-bio.BM:
    Biomolecules"`.

    The slug is in the name because it is what a physicist will
    recognise and what arXiv's own pages show, and the label because
    nobody remembers what `cond-mat.dis-nn` stands for."""
    label = CATEGORY_LABELS.get(slug)
    return ("arXiv {}: {}".format(slug, label) if label
            else "arXiv {}".format(slug))


def feed_url(category):
    return FEED_URL + category


def _http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _text(node):
    return " ".join((node.text or "").split()) if node is not None else None


def arxiv_id(link, guid=None):
    """The bare arXiv ID from an item's link, or its guid.

    `https://arxiv.org/abs/2203.01250` → `2203.01250`, and
    `oai:arXiv.org:2203.01250v3` → `2203.01250`. The version is
    dropped: it belongs to the announcement, not to the paper, and the
    DOI arXiv mints has no version in it either.

    Old-style identifiers (`math/0309136`, used before April 2007)
    keep their archive prefix, which is part of the ID."""
    for raw in (link, guid):
        if not raw:
            continue
        m = re.search(r"(?:abs/|oai:arXiv\.org:)"
                      r"([a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})"
                      r"(?:v\d+)?", raw)
        if m:
            return m.group(1)
    return None


def doi_for(arxiv_identifier):
    """The DOI arXiv mints for every submission.

    Lower-cased because that is the form `extract.py` produces from a
    bare ID and the form `index.normalize_doi` compares, and the
    `discovered` dedupe is on this string."""
    if not arxiv_identifier:
        return None
    return "10.48550/arxiv." + arxiv_identifier.lower()


def _announce_type(item):
    """`new`, `cross`, `replace` or `replace-cross`.

    Read from `arxiv:announce_type` where it is there, and otherwise
    from the `description`, which opens
    `arXiv:2203.01250v3 Announce Type: replace-cross`. Both are in the
    live feed; the fallback is here because the whole filter depends
    on this one value, and guessing `new` for a replacement would
    resurface old papers forever."""
    explicit = _text(item.find(_ARXIV + "announce_type"))
    if explicit:
        return explicit.strip().lower()
    desc = _text(item.find("description")) or ""
    m = re.search(r"Announce Type:\s*([a-z-]+)", desc, re.IGNORECASE)
    return m.group(1).lower() if m else None


def _abstract(item):
    """The abstract out of `description`, which prefixes it with the
    identifier and the announce type:

        arXiv:2203.01250v3 Announce Type: replace-cross
        Abstract: Many works have been devoted to ...
    """
    desc = _text(item.find("description"))
    if not desc:
        return None
    m = re.search(r"Abstract:\s*(.*)$", desc, re.DOTALL)
    text = (m.group(1) if m else desc).strip()
    return text or None


def _authors(raw):
    """`"Antonin Monteil, Paul Pegon"` → display names.

    Already in reading order, unlike bioRxiv's `Surname, Initials`
    form, so this is a split and nothing more."""
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _year(pub_date):
    """The year out of `Fri, 23 Aug 2024 00:00:00 -0400`."""
    m = re.search(r"\b(\d{4})\b", pub_date or "")
    return int(m.group(1)) if m else None


def is_replacement(announce_type):
    """True for `replace` and `replace-cross`.

    A prefix test, not equality: `replace-cross` is a replacement
    announced in a secondary category, and arXiv's own specification
    uses it as its example. Testing `== "replace"` would let half of
    them through, and every one is a paper the feed has shown
    before."""
    return bool(announce_type) and announce_type.startswith("replace")


def parse_feed(xml_bytes, keep_replacements=False):
    """Feed XML → article dicts of the shape `index.upsert_discovered`
    wants.

    Returns [] for anything unparseable — including the valid, empty
    channel served at a weekend, which is not an error. Replacements
    are dropped unless asked for; cross listings are kept, since a
    paper surfacing in a second category is information."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        announce = _announce_type(item)
        if not keep_replacements and is_replacement(announce):
            continue
        link = _text(item.find("link"))
        guid = _text(item.find("guid"))
        ident = arxiv_id(link, guid)
        doi = doi_for(ident)
        if not doi:
            # No identifier means no dedupe key, and `discovered`
            # is keyed on the DOI.
            continue
        pub_date = _text(item.find("pubDate"))
        out.append({
            "doi": doi,
            "title": _text(item.find("title")),
            "authors": _authors(_text(item.find(_DC + "creator"))),
            "abstract": _abstract(item),
            # The server stands in for the journal, as it does for
            # bioRxiv and for Europe PMC preprint rows — even when
            # `arxiv:DOI` says the paper has since been published,
            # because what this row links to is the preprint.
            "journal": "arXiv",
            "year": _year(pub_date),
            "published_date": pub_date,
            # Free to read by construction. The PDF URL is built from
            # the DOI by pdf_fetch rather than advertised here.
            "is_oa": True,
            "oa_status": "green",
            "oa_url": link,
            "announce_type": announce,
            "categories": [c.text.strip() for c in item.findall("category")
                           if c is not None and c.text],
        })
    return out


def fetch_category(category, http_get=None, timeout=30,
                   keep_replacements=False):
    """Articles currently announced for one category, as the feed
    orders them.

    Raises nothing: a feed that fails is empty, which the caller has
    to handle anyway, because an empty feed is also the honest answer
    at a weekend."""
    get = http_get or _http_get
    try:
        raw = get(feed_url(category), timeout=timeout)
    except TypeError:
        try:
            raw = get(feed_url(category))
        except Exception:
            return []
    except Exception:
        return []
    return parse_feed(raw, keep_replacements=keep_replacements)
