# Alexandria

A GTK4-based organizer/reference manager for scientific PDFs.

Alexandria is designed to be a personal and local store. It is not
an interface where you upload your document collection to a cloud
server somewhere. There is no crowdsourcing.
Your PDF catalogue won't be (can't be) part of someone else's data
harvesting. If you want your reading habits and project lists tracked
by corporations, and suggested to others then Alexandria is not for
you.

Alexandria has 3 main "views"
  - PDF viewer: for reading and annotations
  - PDF organizer/reference manager: view, store and update metadata
  - Author view: what's been published (recently), who publishes
    with or cites who?

There is a PDF viewer, based on poppler [1] built-in. One can add
annotations to PDFs.

Alexandria uses OpenAlex and CrossRef network calls and PDF text
extraction to associate metadata [2] with PDF files (`.alexandria`
extension, but JSON inside) - these are the "sidecars."

The file store is a plain old directory with PDF files in it.

An SQLite database is constructed using the sidecars for fast
searching.

There are subscriptions and discovery.

Alexandria uses JATS where it can.

It would not be very wrong to describe Alexandria as a desktop
interface to OpenAlex that knows about PDF files and citation
formats.

Alexandria is intended to be XDG Base Directory Protocol [3] compliant. It
writes, by default, to `$HOME/Documents/Alexandria` and the database to
`$HOME/.local/state/Alexandria` with a config file
in `$HOME/.config/Alexandria/config.json` for sort order config and
OpenAlex key. (A Flatpak install puts all three somewhere else — see
[Configuration](#configuration).)

## Background

Quite some time ago now I had liked John Spray's Referencer:

[https://icculus.org/referencer](https://icculus.org/referencer)

as a local-storage pdf organizer/reference manager. But that seems to no
longer be maintained or updated. Which is why I thought.. maybe I can
make one...

## > [!CAUTION]

> If you cloned Alexandria before 0.5.0 then it's probably best
> to throw away the previous repo and start fresh.
>
> I rewrote the history and removed and recreated the repo to remove
> information that should not have been there.

## Screenshots
![Alexandria main window example](data/screenshots/main-window-screenshot.png)
![Alexandria author view example](data/screenshots/author-window-screenshot.png)


## Install

### Debian / Ubuntu

    apt install python3-gi gir1.2-gtk-4.0 gir1.2-poppler-0.18 poppler-utils
    make install

### Arch Linux

The GTK stack and PyGObject come from pacman — PyGObject has to be
built against the same GTK it will load, so mixing a pip-installed
one with the system libraries is the way to a segfault:

    sudo pacman -S --needed gtk4 libadwaita poppler poppler-glib \
                            python-gobject python-cairo \
                            adwaita-icon-theme librsvg vte4

`poppler-glib` carries the `Poppler-0.18` typelib the viewer imports;
`poppler` provides `pdftotext`, which the text extraction shells out
to. `adwaita-icon-theme` and `librsvg` are what make the toolbar
render as icons rather than broken-image squares. `vte4` is only for
the optional built-in terminal.

The Python dependencies come from pip, and cannot come from pacman:
Arch ships `python-bibtexparser` 1.4.4, while `bibtex.py` uses the
v2 `parse_string` / middlewares API, and `citeproc-py` is not in the
repositories at all.

Arch also marks its system Python as externally managed (PEP 668), so
`pip install --user` refuses to run. Use a virtualenv that can still
see pacman's PyGObject:

    python -m venv --system-site-packages ~/.venvs/alexandria
    make install PYTHON=~/.venvs/alexandria/bin/python

`--system-site-packages` is the load-bearing flag: without it the
venv cannot see `gi` at all, and pip will try to build PyGObject from
source to fill the gap. With it, pip installs only the pure-Python
dependencies and leaves the GTK bindings to pacman.

Then run `~/.venvs/alexandria/bin/alexandria-browse`, or put
`~/.venvs/alexandria/bin` on your `PATH`. The `.desktop` file
`make install` writes calls `alexandria-browse`, so either the venv's
`bin` needs to be on the PATH your desktop session sees, or edit the
`Exec=` line to the absolute path.

To run from the source tree instead, no install is needed once the
pacman packages above are present and the pip dependencies are in
the venv:

    ~/.venvs/alexandria/bin/python alexandria-browse.py

### macOS (Homebrew)

Alexandria is a GTK4 application, so the GTK stack and its
GObject-introspection typelibs have to come from Homebrew — there is
no wheel for them.

    brew install gtk4 libadwaita poppler gobject-introspection \
                 librsvg vte3 adwaita-icon-theme
    brew install pygobject3 py3cairo

    pip install --user .          # or: make install

Use the same Python throughout. Homebrew's `pygobject3` and
`py3cairo` are built for Homebrew's Python, so `pip install` with
that interpreter. If you would rather use your own Python, skip
those two formulae and let pip build PyGObject and pycairo from
source — that works, but only because the Homebrew C libraries
above are already present for it to compile against.

`adwaita-icon-theme` is not optional. Without it GTK falls back to its
small built-in icon set and much of the toolbar renders as
broken-image squares. `librsvg` is what draws SVG icons at all, and
`vte3` provides the optional built-in terminal.

To run from the source tree:

    export XDG_DATA_DIRS=/opt/homebrew/share
    export DYLD_LIBRARY_PATH=/opt/homebrew/lib
    python3 alexandria-browse.py

Both variables are needed because Homebrew installs outside the paths
GLib searches by default. `XDG_DATA_DIRS` in particular is not
optional: without it `Gtk.FileDialog` aborts with "No GSettings
schemas are installed on the system" the first time you open a file.

Or build a `.app` bundle, which gives Alexandria its own Dock icon and
identity instead of inheriting Python's:

    ./make-app.sh          # produces dist/Alexandria.app

Note that `make install` also installs a `.desktop` file and an XDG
icon, which do nothing on macOS but are harmless.

## Configuration

On first run Alexandria writes a starter config file to
`$HOME/.config/Alexandria/config.json`:

    {
      "catalogues": [
        { "name": "default", "library_root": "/home/you/Documents/Alexandria" }
      ],
      "current_catalogue": "default",
      "contact_email": "",
      "openalex_api_key": ""
    }

Everything works with both of those left empty, but neither is
decoration:

**`contact_email`** is your own address, and it is what the metadata
services ask for so they can contact you about a misbehaving client.
OpenAlex and CrossRef give politer rate limits to requests that carry
one — without it you share the anonymous pool, which matters most when
importing a folder of papers. **Unpaywall refuses to answer at all**
without an address, so until you set one, **Get PDF** quietly searches
one source fewer.

**`openalex_api_key`** is free from
[openalex.org](https://openalex.org/) and gives you a private daily
request budget instead of the shared one. Author pages, citation
counts, most of Discover and the reference popover all spend it — but
not Discover's **Preprints** tab, which asks Europe PMC, or **By PDB**,
which asks PDBe; neither needs a key. Without one you are not locked
out, but on a large library you will meet the common pool's rate
limit.

Both can also be set in **Preferences → Online services** rather than
by editing the file, and the file is the same file. The library root
can be overridden for one run with the `ALEXANDRIA_LIBRARY`
environment variable.

**`bibtex_live_path`** is absent until you set it, and names a `.bib`
file Alexandria keeps in step with the library — see
[Writing a paper](#writing-a-paper). Set it in
**Preferences → Live BibTeX**, or by hand:

    "bibtex_live_path": "/home/you/thesis/refs.bib"

### If you installed the Flatpak

The sandbox redirects the XDG directories, so nothing is where the
paths above say. Substitute:

| | |
| --- | --- |
| config | `~/.var/app/io.github.pemsley.Alexandria/config/Alexandria/config.json` |
| databases | `~/.var/app/io.github.pemsley.Alexandria/.local/state/Alexandria/` |
| author photos | `~/.var/app/io.github.pemsley.Alexandria/.local/share/Alexandria/` |

Two consequences worth knowing before you go looking for a bug:

* **A Flatpak install shares nothing with a `pip` install** — not the
  index, not the author trail, not the photographs. The same machine
  can hold two libraries that know nothing of each other.
* **The sandbox can see `~/Documents` and little else.** If your PDFs
  live anywhere else, Alexandria will start with an empty library and
  no explanation. Grant the extra directory with
  [Flatseal](https://flathub.org/apps/com.github.tchx84.Flatseal), or:

      flatpak override --user \
          --filesystem=~/Papers io.github.pemsley.Alexandria

## Usage

Upon opening Alexandria, it will detect PDF files in
`$HOME/Documents/Alexandria` and try to create a thumbnail PNG and the
associated metadata (if they don't already exist).

### Getting papers in

Drop a PDF into `$HOME/Documents/Alexandria` with a file manager, or
drag it onto the Alexandria window — either way a card appears, with
the metadata looked up from the DOI. There is no import dialog to go
through. The hamburger menu also offers **Import from DOI or PubMed
ID…**, **Import BibTeX…**, **Import Files…** and **Import Folder…**.

A BibTeX import makes a card for every entry, including the ones with
no PDF. Those are *ghost* cards: press **Get PDF** and Alexandria
tries OpenAlex, Unpaywall and EuropePMC in turn, and on success merges
the download into the entry. Dropping a PDF straight onto a ghost
card's thumbnail does the same thing.

### Writing a paper

**Preferences → Live BibTeX** points Alexandria at the `.bib` your
LaTeX document cites, and keeps it there — every import, edit and
deletion rewrites the file, so `\cite{}` works without an export
first. Alexandria owns the file: it rewrites the whole thing rather
than appending, so a correction you make in the Edit dialog reaches
an entry already written and a duplicate citation key can't creep in.
Anything you type into the file yourself is lost on the next change,
and choosing a `.bib` that already has content in it asks first.

The file is only written when something actually changed, so
`latexmk -pvc` won't rebuild in a loop. For a one-off snapshot
instead, **Import ▸ Export BibTeX…** still writes whatever the
current search and mark filter have on screen.

### Reading

Click a card's thumbnail to open the viewer. The sidebar has three
modes — **Contents** (the PDF's own table of contents), **Pages**
(thumbnails) and **Highlights** — and F9 toggles it.

The part worth knowing about: **click a citation marker in the body
text**. Alexandria resolves `[12]` against the paper's reference list
and shows the reference right where you are reading — the entry, the
sentence it was cited in, its metadata and an option to add it to
your library — so there is nothing to scroll back from. **Go to
reference** makes the trip to the bibliography when you want it, and
Alt-Left brings you back. This works from the publisher's own
link annotations where they exist, and from the JATS full text or the
printed reference list where they do not.

Select text to highlight it and attach a comment; highlights are
saved in the sidecar and listed in the sidebar.

### Cards

The chips along a card's title tell you about the paper at a glance:
open-access status, licence, whether a correction or retraction has
been registered, whether the full text or JATS is stored locally,
whether it is supplementary material, and — for UK-funded work — the
UKRI grant that paid for it. Hover any of them for the detail.

A **Check metadata** chip means the DOI's record was used but it
disagrees with what the PDF says about itself; **Unverified** means no
DOI resolved to a paper record at all. Either way, open **Edit
metadata** to see both and decide.

### Authors

Click the author list on a card for a popover of its authors, then a
name to open the Author view: what they have published, who they
publish with, who cites them most, their
citing-impact split by whether the citing paper treats the work as
software, method or idea — and, where they are UK-funded, the grants
they hold as PI or Co-I with amounts and dates, from UKRI Gateway to
Research.

Authors you have looked at accumulate in a trail down the left, and
they are shared across catalogues, as are any photographs you attach.

### Keeping up

**Subscriptions** follow a journal, a saved OpenAlex search, bioRxiv
subject collections or arXiv categories, and collect what is new into
a feed refreshed in the background.

Neither preprint server offers a search worth relying on, so their
subscriptions are whole sections. For bioRxiv, tick as many of the 27
collections as you read; for arXiv, as many of the 155 categories,
grouped by archive. Each gets its own feed, and a paper listed under
two sections appears under both — a cross-listing is information, not
a duplicate. The rows arrive complete: title, authors, abstract, DOI
and date come straight from the feed, with no further lookups.

arXiv announces once each weekday and the feed carries one cycle, so
nothing arrives at a weekend. Revised versions of papers already
announced are left out, since they are papers you have been shown
already — without that, half of a typical category is re-runs.
Categories differ enormously in size, from a handful of papers a day
in `q-bio.BM` to several hundred in `cs.LG`, so the feed keeps them in
separate groups rather than one merged list.

To search preprints by term instead, use **Discover → Preprints**,
which asks Europe PMC.

## Notes
- [1] poppler `https://poppler.freedesktop.org/`
- [2] titles, authors, journal, year, DOI, comments
- [3] `https://specifications.freedesktop.org/basedir/latest/`

