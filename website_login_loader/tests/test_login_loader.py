# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""The loader reaches the served auth page, and reaches it inline.

There is no behaviour to assert server side: the module is one template. What
CAN silently break is delivery -- an xpath that stops matching after another
module rewrites the login card, or somebody moving the styles into a bundle,
which would defeat the entire point of the module.
"""
from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged("post_install", "-at_install")
class TestLoginLoader(HttpCase):
    def setUp(self):
        super().setUp()
        self.page = self.url_open("/web/login").text

    def test_loader_markup_is_served_on_the_login_page(self):
        """The xpath still matches whatever the card looks like today."""
        self.assertIn('id="o_cc_ldr"', self.page)
        self.assertIn("o_cc_ldr_bar", self.page)

    def test_curtain_starts_hidden(self):
        """The no-JavaScript guarantee, asserted on the served bytes.

        If this ever renders without `hidden`, a visitor whose browser does not
        run the script gets a permanent cover over the login form.
        """
        self.assertRegex(self.page, r'id="o_cc_ldr"[^>]*hidden')

    def test_styles_and_script_are_inline(self):
        """Not in a bundle, which is the module's whole reason to exist.

        A `<link>` or `<script src>` would arrive inside the render-blocking
        payload whose wait this reports on, so it could only appear once the
        waiting was over.
        """
        self.assertIn(".o_cc_ldr_bar", self.page, "styles inlined in the page")
        self.assertIn("o_cc_loading", self.page, "script inlined in the page")

    def test_live_region_is_present_from_the_start(self):
        """Announcements need a region already in the accessibility tree.

        Revealing a node that was `hidden` is not reliably announced; changing
        the text of a region that was always there is.
        """
        self.assertIn("o_cc_ldr_sr", self.page)
        self.assertIn('aria-live="polite"', self.page)

    # ------------------------------------------------------------------
    # The form slot
    # ------------------------------------------------------------------

    def test_the_skeleton_is_served_where_the_form_will_appear(self):
        """The gap a visitor stares at, occupied by the shape of what is coming.

        Order is the assertion, not mere presence: the skeleton stands in for
        the form, so it has to be in the form's place. Rendered after it, it
        would be a second block below an empty box rather than a stand-in for
        one.
        """
        self.assertIn("o_cc_skel", self.page)
        self.assertLess(
            self.page.index('class="o_cc_skel"'),
            self.page.index("oe_login_form"),
            "the stand-in belongs where the form is going to be",
        )

    def test_the_skeleton_is_hidden_unless_the_script_asks_for_it(self):
        """No JavaScript, no skeleton — and therefore never a stuck one.

        The class that reveals it is added by the page's own script, so a
        browser that never runs the script cannot end up with a skeleton
        nobody is left to take down.
        """
        self.assertIn(".o_cc_skel { display: none; }", self.page)
        self.assertIn("html.o_cc_skel_on .o_cc_skel { display: block; }", self.page)

    def test_load_alone_does_not_take_the_skeleton_down(self):
        """The gap the user photographed on 2026-08-17.

        `load` means every resource arrived, not that the page has anything to
        show: Odoo boots its module system after it, so the account picker
        mounts later and core leaves the form `d-none` until then. Removing
        the skeleton on `load` regardless left a blank card between the logo
        and "o continúa como invitado" -- precisely the wait this module
        exists to cover.

        Asserted on the source because the behaviour is a race no HTTP test
        can observe: what has to be true is that the `load` handler asks
        `ready()` first instead of calling `done()` outright.

        Anchored on `setTimeout(done, MAX_WAIT)` rather than on the listener
        itself: the page carries TWO `load` listeners -- the top progress bar
        registers one as well -- and splitting on that string picks whichever
        comes first, which is not this one.
        """
        handler = self.page.split("setTimeout(done, MAX_WAIT)")[1][:1400]
        self.assertIn("ready()", handler)
        self.assertNotIn(
            "requestAnimationFrame(done)",
            handler,
            "load may finish the wait early, it may not declare it over",
        )

    def test_the_wait_still_has_a_backstop(self):
        """A loader that never stops is worse than one that stops too soon.

        With `load` no longer sufficient, the timeout is the only thing left
        guaranteeing the skeleton comes down if the boot never completes.
        """
        self.assertIn("MAX_WAIT", self.page)
        self.assertIn("setTimeout(done, MAX_WAIT)", self.page)

    def test_the_skeleton_never_hides_the_real_form(self):
        """The one rule that keeps this from locking anybody out.

        Odoo hides the form and Odoo reveals it. If this module ever took
        that decision too, a failure in its own script would be a login page
        with no way in.
        """
        self.assertNotIn("o_cc_skel_on .oe_login_form", self.page)
