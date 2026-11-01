# Copyright 2026 Canarias Conectada
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import http
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestSwitchSameDomain(HttpCase):
    """Switching website must not send the browser to another domain.

    Goes through real HTTP on purpose: the behaviour under test IS the
    ``Location`` header core would have set, and calling the controller
    directly would prove nothing about what a browser does with it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_website = cls.env["website"].create(
            {
                "name": "Switch Target",
                # A domain that is definitely not the test host: without the
                # override this is exactly where the browser would be sent.
                "domain": "https://switch-target.example.com",
            }
        )
        # An editor of its own rather than ``admin``: these tests also run
        # against copies of the live database, where the admin password is the
        # real one and not something a test may assume. The two groups are the
        # ones core's ``website_force`` demands before it will switch at all.
        cls.password = "switch_editor_pw"
        cls.editor = new_test_user(
            cls.env,
            login="switch_editor",
            password=cls.password,
            groups="base.group_user,website.group_multi_website,"
            "website.group_website_restricted_editor",
        )

    def test_switching_stays_on_the_current_domain(self):
        self.authenticate(self.editor.login, self.password)
        response = self.url_open(
            "/website/force/%s?path=%%2Fshop" % self.other_website.id,
            allow_redirects=False,
        )
        location = response.headers.get("Location", "")
        self.assertNotIn(
            "switch-target.example.com",
            location,
            "the switcher must not hop to the target website's own domain",
        )
        self.assertTrue(
            location.endswith("/shop"),
            "the switcher must land on the requested path, got %r" % location,
        )

    def test_the_website_is_actually_forced(self):
        """Staying put must not mean staying on the old website.

        Skipping core's domain hop is only correct because forcing the website
        into the session is what actually decides which site gets rendered, so
        that is what this asserts -- read from the server's own session store,
        not inferred from the response.
        """
        self.authenticate(self.editor.login, self.password)
        self.url_open(
            "/website/force/%s?path=%%2F" % self.other_website.id,
            allow_redirects=False,
        )
        session = http.root.session_store.get(self.session.sid)
        self.assertEqual(
            session.get("force_website_id"),
            self.other_website.id,
            "the selected website must be the one the session now renders",
        )

    def test_the_editor_is_told_not_to_hop_domains_either(self):
        """The half of this that nobody reached.

        Picking a site from the switcher never gets as far as
        `/website/force`: the systray component sends the whole browser to the
        site's domain first, and only the `else` branch of that check asks the
        server at all. So the controller above can be perfectly correct and the
        switch still hops -- which is what happened, and what got reported a
        second time.

        `website_bypass_domain_redirect` is core's own flag for it: read in
        `website_switcher_systray_item.js` and written nowhere, a hook left for
        support. With it on, the component asks the server, and the server is
        where this module already had an answer.

        Read out of the backend page rather than by calling `session_info()`:
        that method builds its answer from `request`, so calling it outside one
        raises -- and what reaches the browser is the thing under test anyway.
        """
        self.authenticate("switch_editor", self.password)
        page = self.url_open("/odoo")
        self.assertEqual(page.status_code, 200)
        self.assertIn(
            '"website_bypass_domain_redirect": true',
            page.text,
            "without this the browser leaves before the controller is asked",
        )
