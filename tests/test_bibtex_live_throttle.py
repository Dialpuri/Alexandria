"""The live `.bib` waits for the library to settle.

`index.CHANGE_SERIAL` moves on every `upsert`/`remove`, and a bulk
import moves it hundreds of times. Rendering the file costs a sidecar
read per paper in the library, so acting on each change would mean a
full-library render every two seconds for the length of the import —
exactly the contention `reload_policy` was written to avoid, and it
measured a 4.7 s main-loop freeze with 33 papers.

It would also undo the reason the file is compared before it is
written: mid-import the text really has changed each time, so every
render writes, and a `latexmk -pvc` watching that `.bib` rebuilds
continuously until the import finishes.

So the tick refuses to act while an import is running, and otherwise
waits for the serial to hold still for a whole tick. Neither brake
needs anything from the import paths, which matters because
`_import_busy` is cleared in two different places — `_end_progress`
for file and folder imports, `_do_import_bib_done` for BibTeX import —
and a trigger hooked to either one would have missed the other.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from alexandria import browse


class _Win:
    """`_bib_live_tick` on a stand-in, counting the syncs it asks for.

    The sync is counted rather than run: what is under test is which
    ticks decide to write, not what gets written."""

    _bib_live_tick = browse.BrowserWindow._bib_live_tick

    def __init__(self, serial=0):
        self._bib_live_serial = serial
        self._bib_live_seen = serial
        self._bib_live_busy = False
        self._import_busy = False
        self.syncs = 0

    def _start_bib_live_sync(self):
        # The real one sets _bib_live_busy and clears it when the
        # worker finishes; here the sync is instantaneous, which is
        # the uninteresting case. Overlap has a test of its own.
        self.syncs += 1


@pytest.fixture
def serial(monkeypatch):
    """Drive `index.CHANGE_SERIAL` by hand."""

    def set_to(n):
        monkeypatch.setattr(browse.index, "CHANGE_SERIAL", n)

    set_to(0)
    return set_to


@pytest.fixture
def enabled(monkeypatch, tmp_path):
    """The feature on, pointed at a path."""
    path = str(tmp_path / "refs.bib")
    monkeypatch.setattr(browse.bibtex_live, "get_path", lambda: path)
    return path


# ---- the ordinary case ----------------------------------------------

def test_one_change_is_written_once_it_has_settled(enabled, serial):
    """A paper arrives: nothing on the tick that sees the change,
    one write on the next quiet tick, and nothing after that."""
    win = _Win()

    serial(1)
    win._bib_live_tick()
    assert win.syncs == 0, "the library may still be moving"

    win._bib_live_tick()
    assert win.syncs == 1

    win._bib_live_tick()
    win._bib_live_tick()
    assert win.syncs == 1, "nothing changed, so nothing is rewritten"


def test_a_quiet_library_never_writes(enabled, serial):
    win = _Win()

    for _ in range(10):
        win._bib_live_tick()

    assert win.syncs == 0


# ---- the burst ------------------------------------------------------

def test_a_burst_writes_once_at_the_end(enabled, serial):
    """The serial moving on every tick is an import in progress,
    whether or not it set the progress bar. 20 changes, one write."""
    win = _Win()

    for n in range(1, 21):
        serial(n)
        win._bib_live_tick()

    assert win.syncs == 0, "not one render while it is still arriving"

    win._bib_live_tick()
    assert win.syncs == 1


def test_an_import_is_left_alone(enabled, serial):
    """With `_import_busy` set, even a serial that has settled is not
    acted on — a folder import pauses between files, and the pause is
    not the end of the import."""
    win = _Win()
    win._import_busy = True

    serial(5)
    for _ in range(10):
        win._bib_live_tick()

    assert win.syncs == 0


def test_the_end_of_an_import_writes_exactly_once(enabled, serial):
    """No hook in `_end_progress` or `_do_import_bib_done`: the first
    quiet tick after `_import_busy` clears does the work, whichever of
    them cleared it."""
    win = _Win()
    win._import_busy = True

    for n in range(1, 6):
        serial(n)
        win._bib_live_tick()

    win._import_busy = False
    win._bib_live_tick()
    assert win.syncs == 1

    for _ in range(5):
        win._bib_live_tick()
    assert win.syncs == 1, "once, not once per imported paper"


# ---- overlap --------------------------------------------------------

def test_a_render_in_flight_is_not_doubled(enabled, serial):
    """A big library takes a while to render. Ticks during it do
    nothing, and the change that arrived meanwhile is picked up after
    it finishes."""
    win = _Win()
    win._bib_live_busy = True

    serial(3)
    for _ in range(5):
        win._bib_live_tick()
    assert win.syncs == 0

    win._bib_live_busy = False
    win._bib_live_tick()          # sees the change
    win._bib_live_tick()          # settled, writes
    assert win.syncs == 1


# ---- switched off ---------------------------------------------------

def test_turning_it_on_does_not_look_like_everything_changed(
        monkeypatch, serial, tmp_path):
    """While off the tick follows the serial without acting, so the
    first tick after a path is chosen has nothing to catch up on —
    Preferences asks for that first write itself."""
    path = str(tmp_path / "refs.bib")
    off = {"on": False}
    monkeypatch.setattr(browse.bibtex_live, "get_path",
                        lambda: path if off["on"] else "")
    win = _Win()

    for n in range(1, 31):
        serial(n)
        win._bib_live_tick()
    assert win.syncs == 0

    off["on"] = True
    for _ in range(5):
        win._bib_live_tick()

    assert win.syncs == 0, "the 30 changes from before are not news"


def test_the_tick_stays_scheduled(enabled, serial):
    """Every path returns True, or the timer stops and the feature
    quietly dies."""
    win = _Win()

    assert win._bib_live_tick() is True
    serial(1)
    assert win._bib_live_tick() is True
    assert win._bib_live_tick() is True
    win._bib_live_busy = True
    assert win._bib_live_tick() is True
    win._bib_live_busy = False
    win._import_busy = True
    assert win._bib_live_tick() is True
