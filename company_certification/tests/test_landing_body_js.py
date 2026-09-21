# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Decisions of the landing body script, executed in `node`.

`static/src/interactions/landing_body_logic.js` is run exactly as it is
served, inside `landing_body_harness.js`. The harness only calls the helpers
and reports; every assertion lives here.

Not covered here (needs a real browser and the asset bundle): the wiring in
`landing_body.js` -- that the interaction starts on `.o_cc_landing_richtext`,
disposes the carousel instance `website.carousel_slider` created, reads the
DOM into the shapes these helpers take, and applies their answers (attributes
set, `click()` dispatched, Bootstrap `Collapse`/`Carousel`/`Modal` called).
Website tours cannot run on this platform today, so that part is checked by
hand in a browser.

`node` ships with the Doodba image the functional tests run in. Its absence
FAILS the suite instead of skipping it: a skipped suite looks green.
"""

import json
import os
import shutil
import subprocess
import tempfile

from odoo.tests import BaseCase, tagged
from odoo.tools.misc import file_path

HARNESS = os.path.join(os.path.dirname(__file__), "landing_body_harness.js")
SOURCE = "company_certification/static/src/interactions/landing_body_logic.js"

LINK = {"hasHref": True}
NO_HREF = {"hasHref": False}

PANELS = [
    {"id": "sustChallenge1", "shown": True},
    {"id": "sustChallenge2", "shown": False},
    {"id": "sustChallenge3", "shown": True},
]


def _call(name, fn, *args):
    return {"name": name, "fn": fn, "args": list(args)}


def _calls():
    calls = [
        _call("carousel", "carouselOptions", False),
        _call("carousel_reduced_motion", "carouselOptions", True),
        _call(
            "accordion_opening_closed_panel", "panelsToClose", PANELS, "sustChallenge2"
        ),
        _call(
            "accordion_reopening_open_panel", "panelsToClose", PANELS, "sustChallenge1"
        ),
        _call("accordion_nothing_open", "panelsToClose", [PANELS[1]], "sustChallenge2"),
        _call("href_plain", "targetIdFromHref", "#collapseSilverEvolucion"),
        _call(
            "href_absolute",
            "targetIdFromHref",
            "https://x.es/certification/silver#odsModal3",
        ),
        _call("href_encoded", "targetIdFromHref", "#evoluci%C3%B3n"),
        _call("href_empty_hash", "targetIdFromHref", "#"),
        _call("href_missing", "targetIdFromHref", None),
        _call(
            "aria_collapse_closed",
            "ariaFor",
            "collapse",
            {"targetId": "p1", "expanded": False},
        ),
        _call(
            "aria_collapse_open",
            "ariaFor",
            "collapse",
            {"targetId": "p1", "expanded": True},
        ),
        _call(
            "aria_modal",
            "ariaFor",
            "modal",
            {"targetId": "odsModal1", "expanded": True},
        ),
        _call("aria_indicator", "ariaFor", "indicator", {"label": "Ecosistema"}),
        _call("aria_without_href", "ariaFor", "close", {"hasHref": False}),
        _call("aria_not_a_trigger", "ariaFor", None, {"targetId": "p1"}),
        _call("label_caption", "indicatorLabel", "  Retos\n  Sociales ", 3),
        _call("label_position", "indicatorLabel", "", 3),
        _call("indicators", "indicatorStates", 4, 2),
        _call("indicators_none", "indicatorStates", 0, 0),
    ]
    for key in (" ", "Spacebar", "Space", "Enter", "Tab", "Escape", "a", "ArrowDown"):
        calls.append(_call("key_link_%s" % key, "keyAction", key, LINK))
        calls.append(_call("key_nohref_%s" % key, "keyAction", key, NO_HREF))
    calls.append(
        _call(
            "key_modified_space", "keyAction", " ", {"hasHref": True, "modified": True}
        )
    )
    for name, trigger in TRIGGER_TABLE.items():
        calls.append(_call("kind_%s" % name, "triggerKind", trigger))
    return calls


# What survives the sanitizer on each trigger of the shipped bodies.
TRIGGER_TABLE = {
    "collapse": {"classes": ["accordion-button", "collapsed"], "toggle": "collapse"},
    "read_more": {
        "classes": ["btn", "btn-primary", "rounded-circle"],
        "toggle": "collapse",
    },
    "modal": {"classes": ["sust-ods-item"], "toggle": "modal"},
    "prev": {"classes": ["carousel-control-prev"], "toggle": None},
    "next": {"classes": ["carousel-control-next"], "toggle": None},
    "close": {"classes": ["btn-close", "btn-close-white", "ms-auto"], "toggle": None},
    "indicator": {"classes": ["active"], "toggle": None, "inIndicators": True},
    "plain_link": {"classes": ["o_cc_landing_card"], "toggle": None},
}
EXPECTED_KINDS = {
    "collapse": "collapse",
    "read_more": "collapse",
    "modal": "modal",
    "prev": "carousel-prev",
    "next": "carousel-next",
    "close": "close",
    "indicator": "indicator",
    "plain_link": None,
}


def _run_harness(calls):
    if not shutil.which("node"):
        raise RuntimeError(
            "company_certification: `node` is required to execute the landing "
            "body helpers under test and was not found on PATH. It ships with "
            "the Doodba image; install nodejs to run this suite locally. "
            "These tests must not be skipped."
        )
    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, "input.json")
        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump({"calls": calls}, handle)
        proc = subprocess.run(
            ["node", HARNESS, file_path(SOURCE), input_path],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        raise AssertionError(
            "the harness produced no result (exit %s)\nstdout: %s\nstderr: %s"
            % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:])
        ) from None
    if "harnessError" in report:
        raise AssertionError("the helpers failed to run:\n%s" % report["harnessError"])
    return report


@tagged("post_install", "-at_install")
class TestLandingBodyJS(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # One `node` run for the class.
        cls.report = _run_harness(_calls())
        cls.results = cls.report["results"]

    # -- carousel -------------------------------------------------------
    def test_the_carousel_plays_by_itself(self):
        # `ride` must be explicit: data-bs-ride does not survive the sanitizer
        # and the core interaction otherwise leaves the carousel paused.
        self.assertEqual(
            self.results["carousel"],
            {"ride": "carousel", "interval": 5000, "rideAttribute": "carousel"},
        )
        self.assertEqual(self.report["constants"], {"interval": 5000})

    def test_reduced_motion_gets_a_still_carousel(self):
        self.assertEqual(
            self.results["carousel_reduced_motion"],
            {"ride": False, "interval": 5000, "rideAttribute": "false"},
        )

    def test_the_active_indicator_follows_the_slide_by_position(self):
        self.assertEqual(self.results["indicators"], [False, False, True, False])
        self.assertEqual(self.results["indicators_none"], [])

    def test_an_indicator_is_named_after_its_slide(self):
        self.assertEqual(self.results["label_caption"], "Retos Sociales")
        self.assertEqual(self.results["label_position"], "4")

    # -- accordion ------------------------------------------------------
    def test_opening_a_panel_closes_the_other_open_ones(self):
        self.assertEqual(
            self.results["accordion_opening_closed_panel"],
            ["sustChallenge1", "sustChallenge3"],
        )

    def test_the_panel_being_opened_is_never_closed(self):
        self.assertEqual(
            self.results["accordion_reopening_open_panel"], ["sustChallenge3"]
        )
        self.assertEqual(self.results["accordion_nothing_open"], [])

    # -- keyboard -------------------------------------------------------
    def test_space_activates_every_trigger(self):
        for key in (" ", "Spacebar", "Space"):
            with self.subTest(key=key):
                self.assertEqual(self.results["key_link_%s" % key], "activate")
                self.assertEqual(self.results["key_nohref_%s" % key], "activate")

    def test_enter_is_left_to_the_browser_on_a_link(self):
        # Handling it too would toggle the panel twice.
        self.assertIsNone(self.results["key_link_Enter"])
        self.assertEqual(self.results["key_nohref_Enter"], "activate")

    def test_other_keys_and_shortcuts_are_not_swallowed(self):
        for key in ("Tab", "Escape", "a", "ArrowDown"):
            with self.subTest(key=key):
                self.assertIsNone(self.results["key_link_%s" % key])
                self.assertIsNone(self.results["key_nohref_%s" % key])
        self.assertIsNone(self.results["key_modified_space"])

    # -- triggers and their ARIA ------------------------------------------
    def test_every_trigger_of_the_bodies_is_recognised(self):
        for name, expected in EXPECTED_KINDS.items():
            with self.subTest(trigger=name):
                self.assertEqual(self.results["kind_%s" % name], expected)

    def test_the_target_comes_from_the_href(self):
        self.assertEqual(self.results["href_plain"], "collapseSilverEvolucion")
        self.assertEqual(self.results["href_absolute"], "odsModal3")
        self.assertEqual(self.results["href_encoded"], "evolución")
        self.assertIsNone(self.results["href_empty_hash"])
        self.assertIsNone(self.results["href_missing"])

    def test_a_collapse_trigger_says_whether_its_panel_is_open(self):
        self.assertEqual(
            self.results["aria_collapse_closed"],
            {"role": "button", "aria-expanded": "false", "aria-controls": "p1"},
        )
        self.assertEqual(self.results["aria_collapse_open"]["aria-expanded"], "true")

    def test_only_a_collapse_trigger_carries_aria_expanded(self):
        self.assertEqual(
            self.results["aria_modal"], {"role": "button", "aria-controls": "odsModal1"}
        )
        self.assertEqual(
            self.results["aria_indicator"],
            {"role": "button", "aria-label": "Ecosistema"},
        )

    def test_a_trigger_without_href_is_made_focusable(self):
        self.assertEqual(
            self.results["aria_without_href"], {"role": "button", "tabindex": "0"}
        )

    def test_what_is_not_a_trigger_is_left_alone(self):
        self.assertEqual(self.results["aria_not_a_trigger"], {})
