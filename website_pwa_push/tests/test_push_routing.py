# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged

MODULE = "@website_pwa_push/js/pwa_push"


@tagged("post_install", "-at_install")
class TestPushRouting(HttpCase):
    """Which worker a subscription belongs to, and the in-app prompt.

    An origin with the installed app runs two workers: the website's (scope
    "/") and core's backend one (scope "/odoo"). A push is handled only by the
    worker of the registration that owns the subscription, so subscribing an
    internal user on the website worker was subscribing them to a worker with
    no push handler (push is off on every website) -- or, with push on, to a
    second copy of every notification.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.website.write({"pwa_enabled": True, "pwa_push_enabled": False})
        # The lab database is a copy of production: "admin" does not log in
        # with "admin", so the test brings a user whose password it knows.
        cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "PWA push internal",
                "login": "pwa_push_internal",
                "password": "pwa_push_internal",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    # ------------------------------------------------------------------
    # The in-app prompt
    # ------------------------------------------------------------------

    def test_signed_in_users_get_the_in_app_prompt(self):
        self.authenticate("pwa_push_internal", "pwa_push_internal")
        html = self.url_open("/").text
        self.assertIn("o_pwa_push_prompt", html)
        self.assertIn('data-pwa-push-standalone="1"', html)
        self.assertIn('data-pwa-push-prompt-only="1"', html)
        self.assertIn("o_pwa_push_dismiss", html)

    def test_the_prompt_does_not_depend_on_the_website_push_switch(self):
        """Internal users are pushed through core's backend worker, so the
        website switch being off (as it is everywhere in production) must not
        hide their prompt. It is already off in this class."""
        self.assertFalse(self.website.pwa_push_enabled)
        self.authenticate("pwa_push_internal", "pwa_push_internal")
        self.assertIn("o_pwa_push_prompt", self.url_open("/").text)

    def test_public_pages_are_untouched(self):
        self.assertNotIn("o_pwa_push_prompt", self.url_open("/").text)

    def test_no_prompt_without_the_app(self):
        self.website.pwa_enabled = False
        self.authenticate("pwa_push_internal", "pwa_push_internal")
        self.assertNotIn("o_pwa_push_prompt", self.url_open("/").text)

    def test_notify_card_on_a_login_page_is_marked_as_such(self):
        html = str(
            self.env["ir.qweb"]._render(
                "website_pwa_push.pwa_notify_card",
                {"pwa_push_context": "login", "pwa_push_standalone": True},
            )
        )
        self.assertIn('data-pwa-push-context="login"', html)
        self.assertIn('data-pwa-push-standalone="1"', html)
        self.assertNotIn("data-pwa-push-prompt-only", html)
        for branch in (
            "o_pwa_push_button",
            "o_pwa_push_done",
            "o_pwa_push_deferred",
            "o_pwa_push_denied",
            "o_pwa_push_ios_hint",
        ):
            self.assertRegex(html, rf'class="[^"]*{branch}[^"]*d-none')

    # ------------------------------------------------------------------
    # The page script, executed in the browser
    # ------------------------------------------------------------------

    def _run(self, checks):
        """Run assertions against the page module in a real browser.

        No hoot suite exists for the website bundle, so the exported pure
        functions are exercised through the module loader of a real page.
        """
        code = f"""
            const mod = odoo.loader.modules.get("{MODULE}");
            const failures = [];
            const check = (label, actual, expected) => {{
                if (JSON.stringify(actual) !== JSON.stringify(expected)) {{
                    failures.push(label + ": got " + JSON.stringify(actual));
                }}
            }};
            {checks}
            if (failures.length) {{
                console.error(failures.join(" | "));
            }} else {{
                console.log("test successful");
            }}
        """
        self.browser_js("/", code, ready=f"!!odoo.loader.modules.get('{MODULE}')")

    def test_push_target_routing(self):
        self._run(
            """
            const t = (o) => mod.pushTarget(Object.assign({
                isInternalUser: false, isLoggedIn: false,
                websitePushEnabled: false, loginContext: false,
            }, o));
            check("internal user -> backend worker",
                t({isInternalUser: true, isLoggedIn: true}), "backend");
            check("internal user, website push on -> still backend",
                t({isInternalUser: true, isLoggedIn: true, websitePushEnabled: true}),
                "backend");
            check("anonymous on login page -> deferred",
                t({loginContext: true}), "deferred");
            check("anonymous on login page, push on -> still deferred",
                t({loginContext: true, websitePushEnabled: true}), "deferred");
            check("portal user, push on -> website worker",
                t({isLoggedIn: true, websitePushEnabled: true}), "website");
            check("portal user, push off -> nothing to offer",
                t({isLoggedIn: true}), null);
            check("anonymous elsewhere, push off -> nothing",
                t({}), null);
            """
        )

    def test_open_channel_url(self):
        self._run(
            """
            check("channel", mod.discussChannelUrl(7),
                "/odoo/action-mail.action_discuss?active_id=discuss.channel_7");
            check("call", mod.discussChannelUrl("7", true),
                "/odoo/action-mail.action_discuss?active_id=discuss.channel_7&call=accept");
            check("path injection", mod.discussChannelUrl("7/../../x"), null);
            check("zero", mod.discussChannelUrl(0), null);
            check("missing", mod.discussChannelUrl(undefined), null);
            """
        )

    def test_vapid_key_round_trip(self):
        self._run(
            """
            const key = "BAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7PD0-P0A";
            const bytes = mod.base64UrlToUint8Array(key);
            check("length", bytes.length, 65);
            check("round trip", mod.arrayBufferToBase64Url(bytes.buffer), key);
            """
        )
