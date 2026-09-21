# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Behaviour of the SHIPPED frontend code, executed in `node`.

`shared_consent_cookie.js` AND `consent_cookie_patches.js` are run as they are
served, together with core's real `patch`, `cookie` and the `website` patch of
`cookie.set`, inside `shared_consent_harness.js`, against an emulated browser
cookie store. The harness only observes and reports; every assertion lives
here. See the harness header for what is real and what is faked.

Not covered here (needs a real browser and the asset bundle): the real
`CookiesBar`/`Popup` classes and the bundle's actual module load order.

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

from .test_shared_domain import DOMAIN, HOST_GUARD_TABLE, NORMALIZE_TABLE, SHOP_HOST

HARNESS = os.path.join(os.path.dirname(__file__), "shared_consent_harness.js")
PATCHES = "@website_cookies_bar_shared_domain/js/consent_cookie_patches"
WEBSITE_COOKIE_PATCH = "@website/js/http_cookie"
MODULES = {
    "@web/core/utils/patch": "web/static/src/core/utils/patch.js",
    "@web/core/browser/cookie": "web/static/src/core/browser/cookie.js",
    WEBSITE_COOKIE_PATCH: "website/static/src/js/http_cookie.js",
    "@website_cookies_bar_shared_domain/js/shared_consent_cookie": (
        "website_cookies_bar_shared_domain/static/src/js/shared_consent_cookie.js"
    ),
    PATCHES: (
        "website_cookies_bar_shared_domain/static/src/js/consent_cookie_patches.js"
    ),
}

COOKIE = "website_cookies_bar"
PORTAL_HOST = DOMAIN
OTHER_SHOP_HOST = "otra.canariasconectada.es"
UNKNOWN_SUFFIX = "tenant-hosting.net"
DAY = 24 * 60 * 60
FULL_TTL = 999 * DAY
NOW = 1_700_000_000_000


def consent(optional, days_ago):
    """A consent in core's exact format, given `days_ago` days before NOW."""
    return '{"required": true, "optional": %s, "ts": %d}' % (
        "true" if optional else "false",
        NOW - days_ago * DAY * 1000,
    )


ACCEPTED = consent(True, 10)
REFUSED = consent(False, 3)


def ttl_left(days_ago):
    return FULL_TTL - days_ago * DAY


def _raw(host, value, domain=None, max_age=FULL_TTL, protocol="https:"):
    """A cookie exactly as core (no domain) or another host (domain) wrote it."""
    cookie = "%s=%s; path=/; max-age=%d" % (COOKIE, value, max_age)
    if domain:
        cookie += "; domain=%s; SameSite=Lax; Secure" % domain
    return {"op": "raw", "host": host, "protocol": protocol, "cookie": cookie}


def _set(host, value, ttl=FULL_TTL, protocol="https:", **extra):
    return dict(
        {"op": "set", "host": host, "protocol": protocol, "value": value, "ttl": ttl},
        **extra,
    )


def _setup(host, protocol="https:"):
    """A page view: `CookiesBar.setup()`; answers "was the bar answered?"."""
    return {"op": "setup", "host": host, "protocol": protocol}


def _read(host):
    return {"op": "read", "host": host}


def _case(name, steps, configured=DOMAIN, **extra):
    session = {} if configured is None else {"cookies_bar_shared_domain": configured}
    return dict({"name": name, "now": NOW, "session": session, "steps": steps}, **extra)


def _conflict(name, shared, host_only):
    """A shared consent (written elsewhere) and a host-only one on SHOP_HOST."""
    return _case(
        name,
        [
            _raw(OTHER_SHOP_HOST, shared, domain=DOMAIN, max_age=12345),
            _raw(SHOP_HOST, host_only),
            _setup(SHOP_HOST),
            _read(SHOP_HOST),
            _read(PORTAL_HOST),
            _read(OTHER_SHOP_HOST),
        ],
    )


def _cases():
    return [
        _case(
            "guard",
            [
                {"op": "guard", "host": host, "configured": DOMAIN}
                for host, _expected in HOST_GUARD_TABLE
            ],
        ),
        _case(
            "normalize",
            [{"op": "normalize", "value": raw} for raw, _ in NORMALIZE_TABLE],
        ),
        _case(
            "resolve",
            [
                {"op": "resolve", "values": values}
                for values in (
                    [consent(True, 1), consent(False, 30)],
                    [consent(False, 30), consent(True, 1)],
                    [consent(True, 30), consent(True, 1)],
                    [consent(False, 1), consent(False, 30)],
                    ["true", consent(True, 1)],
                    [consent(False, 1), "{not json"],
                    ["true", "{not json", '"a string"', "null", '{"required": true}'],
                    [],
                )
            ],
        ),
        _case(
            "write_on_shop",
            [
                _set(SHOP_HOST, ACCEPTED),
                _read(PORTAL_HOST),
                _read(OTHER_SHOP_HOST),
                _read("mitienda.com"),
            ],
        ),
        _case("write_on_portal", [_set(PORTAL_HOST, ACCEPTED), _read(SHOP_HOST)]),
        _case("write_over_http", [_set(SHOP_HOST, ACCEPTED, protocol="http:")]),
        _case("write_default_ttl", [_set(SHOP_HOST, ACCEPTED, ttl=None)]),
        _case(
            "write_expires_host_only_duplicate",
            [_raw(SHOP_HOST, REFUSED), _set(SHOP_HOST, ACCEPTED), _read(SHOP_HOST)],
        ),
        _case(
            "preference_change_propagates",
            [
                _set(SHOP_HOST, ACCEPTED),
                _set(OTHER_SHOP_HOST, REFUSED),
                _read(SHOP_HOST),
                _read(PORTAL_HOST),
            ],
        ),
        _case(
            "delete",
            [
                _set(OTHER_SHOP_HOST, ACCEPTED),
                _raw(SHOP_HOST, REFUSED),
                {"op": "delete", "host": SHOP_HOST},
                _read(SHOP_HOST),
                _read(OTHER_SHOP_HOST),
            ],
        ),
        _case(
            # Any other key is core's business, including the consent gate the
            # `website` patch applies to optional cookies.
            "other_keys_untouched",
            [
                _set(SHOP_HOST, "es_ES", key="frontend_lang", ttl=3600),
                _set(OTHER_SHOP_HOST, REFUSED),
                _set(SHOP_HOST, "x", key="utm_refused", ttl=3600, type="optional"),
                _set(OTHER_SHOP_HOST, ACCEPTED),
                _set(SHOP_HOST, "x", key="utm_accepted", ttl=3600, type="optional"),
            ],
        ),
        _case(
            "outside_the_domain",
            [
                _raw("localhost", ACCEPTED, protocol="http:"),
                _setup("localhost", protocol="http:"),
                _set("localhost", REFUSED, protocol="http:"),
                _set("mitienda.com", ACCEPTED),
            ],
        ),
        _case("parameter_empty", [_set(SHOP_HOST, ACCEPTED)], configured=""),
        _case("parameter_absent", [_set(SHOP_HOST, ACCEPTED)], configured=None),
        _case("parameter_invalid", [_set(SHOP_HOST, ACCEPTED)], configured="es"),
        _case(
            "promote_host_only",
            [
                _raw(SHOP_HOST, ACCEPTED),
                _setup(SHOP_HOST),
                _read(SHOP_HOST),
                _read(OTHER_SHOP_HOST),
                # Second page view: nothing left to do.
                _setup(SHOP_HOST),
            ],
        ),
        # -- two consents at once: decided on the values ------------------
        _conflict("old_shared_accept_new_host_only_refuse", consent(True, 90), REFUSED),
        _conflict(
            "old_shared_refuse_new_host_only_accept", consent(False, 90), ACCEPTED
        ),
        _conflict("new_shared_refuse_old_host_only_accept", REFUSED, consent(True, 90)),
        _conflict(
            "new_shared_accept_old_host_only_refuse", ACCEPTED, consent(False, 90)
        ),
        _conflict("same_answer_host_only_newer", consent(True, 90), ACCEPTED),
        _conflict("same_answer_shared_newer", ACCEPTED, consent(True, 90)),
        _conflict("unparsable_shared", "true", ACCEPTED),
        _conflict("unparsable_host_only", REFUSED, "{not json"),
        _conflict("both_unparsable", "true", "{not json"),
        _case("promote_nothing", [_setup(SHOP_HOST)]),
        _case("promote_legacy", [_raw(SHOP_HOST, "true"), _setup(SHOP_HOST)]),
        _case(
            "promote_expired", [_raw(SHOP_HOST, consent(True, 1000)), _setup(SHOP_HOST)]
        ),
        _case(
            "promote_without_ts",
            [
                _raw(SHOP_HOST, '{"required": true, "optional": true}'),
                _setup(SHOP_HOST),
            ],
        ),
        _case(
            # RFC-literal browser on the bare domain: host-only and Domain
            # cookies are one and the same cookie there.
            "strict_identity_portal",
            [
                _raw(PORTAL_HOST, REFUSED),
                _setup(PORTAL_HOST),
                _read(SHOP_HOST),
                _set(PORTAL_HOST, consent(True, 0)),
                _read(SHOP_HOST),
            ],
            strictIdentity=True,
        ),
        _case(
            # A public suffix neither validator knows: the browser refuses the
            # Domain cookie, and the consent must survive host-only.
            "browser_refuses_domain",
            [
                _raw("foo." + UNKNOWN_SUFFIX, ACCEPTED),
                _setup("foo." + UNKNOWN_SUFFIX),
                _set("foo." + UNKNOWN_SUFFIX, REFUSED),
                _read("foo." + UNKNOWN_SUFFIX),
                _read("bar." + UNKNOWN_SUFFIX),
                {
                    "op": "writeHelper",
                    "host": "foo." + UNKNOWN_SUFFIX,
                    "domain": UNKNOWN_SUFFIX,
                    "value": ACCEPTED,
                    "ttl": FULL_TTL,
                },
            ],
            configured=UNKNOWN_SUFFIX,
            publicSuffixes=[UNKNOWN_SUFFIX],
        ),
        _case(
            # Same story with this module's patch loaded BEFORE website's.
            "reversed_load_order",
            [
                _raw(SHOP_HOST, ACCEPTED),
                _setup(SHOP_HOST),
                _set(OTHER_SHOP_HOST, REFUSED),
                _set(SHOP_HOST, "x", key="utm_refused", ttl=3600, type="optional"),
                {"op": "delete", "host": PORTAL_HOST},
            ],
            loadOrder=[PATCHES, WEBSITE_COOKIE_PATCH],
        ),
    ]


def _run_harness(cases):
    if not shutil.which("node"):
        raise RuntimeError(
            "website_cookies_bar_shared_domain: `node` is required to execute "
            "the frontend code under test and was not found on PATH. It "
            "ships with the Doodba image; install nodejs to run this suite "
            "locally. These tests must not be skipped."
        )
    modules = {name: file_path(path) for name, path in MODULES.items()}
    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, "input.json")
        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump({"modules": modules, "cases": cases}, handle)
        proc = subprocess.run(
            ["node", HARNESS, input_path],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        raise AssertionError(
            "the harness produced no result (exit %s)\nstdout: %s\nstderr: %s"
            % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:])
        ) from None
    if "harnessError" in result:
        raise AssertionError(
            "the frontend code failed to run:\n%s" % result["harnessError"]
        )
    return result["cases"]


def _host_only(host, value, max_age=FULL_TTL, name=COOKIE):
    """A cookie as core writes it: no domain, no SameSite, no Secure."""
    return {
        "name": name,
        "value": value,
        "domain": host,
        "hostOnly": True,
        "path": "/",
        "maxAge": max_age,
        "sameSite": None,
        "secure": False,
    }


def _shared(value, max_age=FULL_TTL, secure=True, domain=DOMAIN):
    return {
        "name": COOKIE,
        "value": value,
        "domain": domain,
        "hostOnly": False,
        "path": "/",
        "maxAge": max_age,
        "sameSite": "Lax",
        "secure": secure,
    }


@tagged("post_install", "-at_install")
class TestSharedConsentJS(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # One `node` run for the class; every case gets its own realm (fresh
        # modules, fresh patches) and its own cookie store.
        cls.cases = _run_harness(_cases())

    def _results(self, name):
        return self.cases[name]["results"]

    def _cookies(self, name):
        return self.cases[name]["cookies"]

    # -- pure helpers -------------------------------------------------------

    def test_constants_match_core(self):
        self.assertEqual(
            self.cases["guard"]["constants"],
            {"CONSENT_COOKIE": COOKIE, "DEFAULT_TTL": 365 * DAY},
        )

    def test_guard_agrees_with_python(self):
        self.assertEqual(
            self._results("guard"), [expected for _host, expected in HOST_GUARD_TABLE]
        )

    def test_normalize_agrees_with_python(self):
        self.assertEqual(
            self._results("normalize"),
            [expected for _raw_value, expected in NORMALIZE_TABLE],
        )

    def test_resolution_rule(self):
        self.assertEqual(
            self._results("resolve"),
            [
                # A refusal beats an acceptance, newer or older, either order.
                consent(False, 30),
                consent(False, 30),
                # Same answer: the most recent one.
                consent(True, 1),
                consent(False, 1),
                # Unparsable values count as absent.
                consent(True, 1),
                consent(False, 1),
                None,
                None,
            ],
        )

    # -- writing, through the shipped patches -------------------------------

    def test_write_on_a_shop_reaches_portal_and_other_shops(self):
        seen = "%s=%s" % (COOKIE, ACCEPTED)
        self.assertEqual(self._results("write_on_shop"), [None, seen, seen, ""])
        self.assertEqual(self._cookies("write_on_shop"), [_shared(ACCEPTED)])

    def test_write_on_the_portal_reaches_the_shops(self):
        self.assertEqual(
            self._results("write_on_portal")[1], "%s=%s" % (COOKIE, ACCEPTED)
        )
        self.assertEqual(self._cookies("write_on_portal"), [_shared(ACCEPTED)])

    def test_secure_only_on_https(self):
        self.assertEqual(
            self._cookies("write_over_http"), [_shared(ACCEPTED, secure=False)]
        )

    def test_default_lifetime_is_core_s(self):
        self.assertEqual(
            self._cookies("write_default_ttl"), [_shared(ACCEPTED, max_age=365 * DAY)]
        )

    def test_write_expires_the_host_only_duplicate(self):
        name = "write_expires_host_only_duplicate"
        self.assertEqual(self._results(name)[2], "%s=%s" % (COOKIE, ACCEPTED))
        self.assertEqual(self._cookies(name), [_shared(ACCEPTED)])

    def test_preference_change_propagates(self):
        name = "preference_change_propagates"
        seen = "%s=%s" % (COOKIE, REFUSED)
        self.assertEqual(self._results(name)[2:], [seen, seen])
        self.assertEqual(self._cookies(name), [_shared(REFUSED)])

    def test_delete_removes_both_cookies(self):
        self.assertEqual(self._results("delete")[3:], ["", ""])
        self.assertEqual(self._cookies("delete"), [])

    def test_other_keys_are_left_to_core(self):
        self.assertEqual(
            self._cookies("other_keys_untouched"),
            [
                _shared(ACCEPTED),
                _host_only(SHOP_HOST, "es_ES", max_age=3600, name="frontend_lang"),
                # Written only once the (shared) consent allowed it.
                _host_only(SHOP_HOST, "x", max_age=3600, name="utm_accepted"),
            ],
        )

    # -- the guard, through the shipped patches -----------------------------

    def test_hosts_outside_the_domain_keep_core_s_cookie(self):
        self.assertEqual(self._results("outside_the_domain")[1], True)
        self.assertEqual(
            self._cookies("outside_the_domain"),
            [_host_only("localhost", REFUSED), _host_only("mitienda.com", ACCEPTED)],
        )

    def test_empty_absent_or_invalid_parameter_is_core_behaviour(self):
        for name in ("parameter_empty", "parameter_absent", "parameter_invalid"):
            with self.subTest(case=name):
                self.assertEqual(self._cookies(name), [_host_only(SHOP_HOST, ACCEPTED)])

    # -- migration ----------------------------------------------------------

    def test_promotion_of_a_host_only_consent(self):
        name = "promote_host_only"
        seen = "%s=%s" % (COOKIE, ACCEPTED)
        # The bar counts as answered on that very page view.
        self.assertEqual(self._results(name)[1:], [True, seen, seen, True])
        # The consent keeps the age it had: promoting is not renewing.
        self.assertEqual(self._cookies(name), [_shared(ACCEPTED, max_age=ttl_left(10))])

    def _assert_conflict(self, name, winner, max_age):
        seen = "%s=%s" % (COOKIE, winner)
        self.assertEqual(self._results(name)[2:], [True, seen, seen, seen])
        self.assertEqual(self._cookies(name), [_shared(winner, max_age=max_age)])

    def test_newer_refusal_beats_an_older_shared_acceptance(self):
        # The BLOCKER of the risk review: refuse everywhere, with the lifetime
        # the refusal's own `ts` leaves it.
        self._assert_conflict(
            "old_shared_accept_new_host_only_refuse", REFUSED, ttl_left(3)
        )

    def test_older_refusal_beats_a_newer_acceptance(self):
        # Deliberate asymmetry: a cookie can only ever narrow the consent. To
        # accept again the visitor uses the bar, which writes the shared
        # cookie directly. 12345: the shared cookie was not even rewritten.
        self._assert_conflict(
            "old_shared_refuse_new_host_only_accept", consent(False, 90), 12345
        )
        self._assert_conflict("new_shared_refuse_old_host_only_accept", REFUSED, 12345)
        self._assert_conflict(
            "new_shared_accept_old_host_only_refuse",
            consent(False, 90),
            ttl_left(90),
        )

    def test_same_answer_the_newest_wins(self):
        self._assert_conflict("same_answer_host_only_newer", ACCEPTED, ttl_left(10))
        self._assert_conflict("same_answer_shared_newer", ACCEPTED, 12345)

    def test_an_unparsable_value_counts_as_absent(self):
        self._assert_conflict("unparsable_shared", ACCEPTED, ttl_left(10))
        self._assert_conflict("unparsable_host_only", REFUSED, 12345)

    def test_two_unparsable_values_are_left_to_core(self):
        # Host-only gone; the legacy shared value is core's to delete, which
        # it does through the patched `cookie.delete` and on the server.
        self.assertEqual(
            self._cookies("both_unparsable"), [_shared("true", max_age=12345)]
        )

    def test_nothing_to_promote(self):
        self.assertEqual(self._results("promote_nothing"), [False])
        self.assertEqual(self._cookies("promote_nothing"), [])

    def test_legacy_and_expired_consents_are_not_promoted(self):
        for name in ("promote_legacy", "promote_expired"):
            with self.subTest(case=name):
                self.assertEqual(self._results(name)[1], False)
                self.assertEqual(self._cookies(name), [])

    def test_consent_without_ts_gets_the_full_lifetime(self):
        self.assertEqual(
            self._cookies("promote_without_ts"),
            [_shared('{"required": true, "optional": true}')],
        )

    # -- browsers -----------------------------------------------------------

    def test_rfc_literal_cookie_identity_on_the_bare_domain(self):
        name = "strict_identity_portal"
        self.assertEqual(
            self._results(name)[1:],
            [
                True,
                "%s=%s" % (COOKIE, REFUSED),
                None,
                "%s=%s" % (COOKIE, consent(True, 0)),
            ],
        )
        self.assertEqual(self._cookies(name), [_shared(consent(True, 0))])

    def test_consent_survives_a_browser_refusing_the_domain(self):
        name = "browser_refuses_domain"
        host = "foo." + UNKNOWN_SUFFIX
        self.assertEqual(
            self._results(name)[1:],
            [True, None, "%s=%s" % (COOKIE, REFUSED), "", "host-only"],
        )
        self.assertEqual(self._cookies(name), [_host_only(host, ACCEPTED)])

    def test_patch_order_does_not_matter(self):
        self.assertEqual(self._results("reversed_load_order")[1], True)
        self.assertEqual(self._cookies("reversed_load_order"), [])
