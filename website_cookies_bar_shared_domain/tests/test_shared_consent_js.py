# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Behaviour of the SHIPPED frontend helpers, executed in `node`.

`static/src/js/shared_consent_cookie.js` is run as it is served, inside
`shared_consent_harness.js`, against an emulated browser cookie store. The
harness only observes and reports; every assertion lives here.

Not covered here (needs a real browser and the asset bundle):
`consent_cookie_patches.js`, i.e. the wiring of these helpers into
`cookie.set` and `CookiesBar.setup`.

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
SOURCE = "website_cookies_bar_shared_domain/static/src/js/shared_consent_cookie.js"

OTHER_SHOP_HOST = "otra.canariasconectada.es"
GIVEN_AT = 1_700_000_000_000
DAY = 24 * 60 * 60
FULL_TTL = 999 * DAY
# Ten days after the consent was given.
NOW = GIVEN_AT + 10 * DAY * 1000

ACCEPTED = '{"required": true, "optional": true, "ts": %d}' % GIVEN_AT
REFUSED = '{"required": true, "optional": false, "ts": %d}' % (GIVEN_AT + 5000)


def _host_only(host, value, protocol="https:"):
    """The cookie exactly as core writes it."""
    return {
        "op": "raw",
        "host": host,
        "protocol": protocol,
        "cookie": "website_cookies_bar=%s; path=/; max-age=%d" % (value, FULL_TTL),
    }


def _write(host, value, ttl=FULL_TTL, configured=DOMAIN, protocol="https:"):
    return {
        "op": "write",
        "host": host,
        "protocol": protocol,
        "configured": configured,
        "value": value,
        "ttl": ttl,
    }


def _promote(host, configured=DOMAIN, protocol="https:"):
    return {
        "op": "promote",
        "host": host,
        "protocol": protocol,
        "configured": configured,
        "ttl": FULL_TTL,
        "now": NOW,
    }


def _read(host):
    return {"op": "read", "host": host}


def _cases():
    return [
        {
            "name": "guard",
            "steps": [
                {"op": "guard", "host": host, "configured": DOMAIN}
                for host, _expected in HOST_GUARD_TABLE
            ],
        },
        {
            "name": "normalize",
            "steps": [{"op": "normalize", "value": raw} for raw, _ in NORMALIZE_TABLE],
        },
        {
            "name": "write_on_shop",
            "steps": [
                _write(SHOP_HOST, ACCEPTED),
                _read(DOMAIN),
                _read(OTHER_SHOP_HOST),
                _read("mitienda.com"),
            ],
        },
        {
            "name": "write_on_portal",
            "steps": [_write(DOMAIN, ACCEPTED), _read(SHOP_HOST)],
        },
        {
            "name": "write_over_http",
            "steps": [_write(SHOP_HOST, ACCEPTED, protocol="http:")],
        },
        {
            "name": "write_expires_host_only_duplicate",
            "steps": [
                _host_only(SHOP_HOST, REFUSED),
                _write(SHOP_HOST, ACCEPTED),
                _read(SHOP_HOST),
            ],
        },
        {
            "name": "preference_change_propagates",
            "steps": [
                _write(SHOP_HOST, ACCEPTED),
                _write(OTHER_SHOP_HOST, REFUSED),
                _read(SHOP_HOST),
                _read(DOMAIN),
            ],
        },
        {
            "name": "delete",
            "steps": [
                _write(OTHER_SHOP_HOST, ACCEPTED),
                _host_only(SHOP_HOST, REFUSED),
                _write(SHOP_HOST, "kill", ttl=0),
                _read(SHOP_HOST),
            ],
        },
        {
            "name": "guarded_hosts",
            "steps": [
                _host_only("localhost", ACCEPTED, protocol="http:"),
                _promote("localhost", protocol="http:"),
                _write("localhost", REFUSED, protocol="http:"),
                _promote("mitienda.com"),
                _promote(SHOP_HOST, configured=""),
                _promote(SHOP_HOST, configured="es"),
            ],
        },
        {
            "name": "promote_host_only",
            "steps": [
                _host_only(SHOP_HOST, ACCEPTED),
                _promote(SHOP_HOST),
                _read(SHOP_HOST),
                _read(OTHER_SHOP_HOST),
                # Second page view: nothing left to do.
                _promote(SHOP_HOST),
            ],
        },
        {
            "name": "promote_shared_wins",
            "steps": [
                _host_only(SHOP_HOST, ACCEPTED),
                _write(OTHER_SHOP_HOST, REFUSED),
                _read(SHOP_HOST),
                _promote(SHOP_HOST),
                _read(SHOP_HOST),
            ],
        },
        {"name": "promote_nothing", "steps": [_promote(SHOP_HOST)]},
        {
            "name": "promote_legacy",
            "steps": [_host_only(SHOP_HOST, "true"), _promote(SHOP_HOST)],
        },
        {
            "name": "promote_expired",
            "steps": [
                _host_only(
                    SHOP_HOST,
                    '{"required": true, "optional": true, "ts": %d}'
                    % (NOW - (FULL_TTL + DAY) * 1000),
                ),
                _promote(SHOP_HOST),
            ],
        },
        {
            "name": "promote_without_ts",
            "steps": [
                _host_only(SHOP_HOST, '{"required": true, "optional": true}'),
                _promote(SHOP_HOST),
            ],
        },
        {
            # RFC-literal browser on the bare domain: host-only and Domain
            # cookies are one and the same cookie there.
            "name": "strict_identity_portal",
            "strictIdentity": True,
            "steps": [
                _host_only(DOMAIN, REFUSED),
                _promote(DOMAIN),
                _read(SHOP_HOST),
                _write(DOMAIN, ACCEPTED),
                _read(SHOP_HOST),
            ],
        },
        {
            # A public suffix the validation heuristic does not know: the
            # browser refuses the Domain cookie, the consent must survive.
            "name": "browser_refuses_domain",
            "publicSuffixes": ["blogspot.com"],
            "steps": [
                _host_only("foo.blogspot.com", ACCEPTED),
                _promote("foo.blogspot.com", configured="blogspot.com"),
                _write("foo.blogspot.com", REFUSED, configured="blogspot.com"),
                _read("foo.blogspot.com"),
                _read("bar.blogspot.com"),
            ],
        },
    ]


def _run_harness(cases):
    if not shutil.which("node"):
        raise RuntimeError(
            "website_cookies_bar_shared_domain: `node` is required to execute "
            "the frontend helpers under test and was not found on PATH. It "
            "ships with the Doodba image; install nodejs to run this suite "
            "locally. These tests must not be skipped."
        )
    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, "input.json")
        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump({"cases": cases}, handle)
        proc = subprocess.run(
            ["node", HARNESS, file_path(SOURCE), input_path],
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
        raise AssertionError("the helpers failed to run:\n%s" % result["harnessError"])
    return result


@tagged("post_install", "-at_install")
class TestSharedConsentJS(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # One `node` run for the class; every case gets its own cookie store.
        cls.report = _run_harness(_cases())

    def _case(self, name):
        return self.report["cases"][name]

    def _shared(self, value, max_age=FULL_TTL, secure=True):
        return {
            "name": "website_cookies_bar",
            "value": value,
            "domain": DOMAIN,
            "hostOnly": False,
            "path": "/",
            "maxAge": max_age,
            "sameSite": "Lax",
            "secure": secure,
        }

    def test_constants_match_core(self):
        self.assertEqual(
            self.report["constants"],
            {"cookie": "website_cookies_bar", "defaultTtl": 365 * DAY},
        )

    def test_guard_agrees_with_python(self):
        self.assertEqual(
            self._case("guard")["results"],
            [expected for _host, expected in HOST_GUARD_TABLE],
        )

    def test_normalize_agrees_with_python(self):
        self.assertEqual(
            self._case("normalize")["results"],
            [expected for _raw, expected in NORMALIZE_TABLE],
        )

    def test_write_on_a_shop_reaches_portal_and_other_shops(self):
        case = self._case("write_on_shop")
        consent = "website_cookies_bar=" + ACCEPTED
        self.assertEqual(case["results"], ["shared", consent, consent, ""])
        self.assertEqual(case["cookies"], [self._shared(ACCEPTED)])

    def test_write_on_the_portal_reaches_the_shops(self):
        case = self._case("write_on_portal")
        self.assertEqual(case["results"], ["shared", "website_cookies_bar=" + ACCEPTED])
        self.assertEqual(case["cookies"], [self._shared(ACCEPTED)])

    def test_secure_only_on_https(self):
        self.assertEqual(
            self._case("write_over_http")["cookies"],
            [self._shared(ACCEPTED, secure=False)],
        )

    def test_write_expires_the_host_only_duplicate(self):
        case = self._case("write_expires_host_only_duplicate")
        self.assertEqual(
            case["results"][1:], ["shared", "website_cookies_bar=" + ACCEPTED]
        )
        self.assertEqual(case["cookies"], [self._shared(ACCEPTED)])

    def test_preference_change_propagates(self):
        case = self._case("preference_change_propagates")
        consent = "website_cookies_bar=" + REFUSED
        self.assertEqual(case["results"], ["shared", "shared", consent, consent])
        self.assertEqual(case["cookies"], [self._shared(REFUSED)])

    def test_delete_removes_both_cookies(self):
        case = self._case("delete")
        self.assertEqual(case["results"][2:], ["deleted", ""])
        self.assertEqual(case["cookies"], [])

    def test_hosts_outside_the_domain_are_left_alone(self):
        case = self._case("guarded_hosts")
        self.assertEqual(case["results"][1:], ["guarded"] * 5)
        self.assertEqual(len(case["cookies"]), 1)
        self.assertEqual(case["cookies"][0]["domain"], "localhost")
        self.assertTrue(case["cookies"][0]["hostOnly"])
        self.assertEqual(case["cookies"][0]["value"], ACCEPTED)

    def test_promotion_of_a_host_only_consent(self):
        case = self._case("promote_host_only")
        consent = "website_cookies_bar=" + ACCEPTED
        self.assertEqual(case["results"][1:], ["promoted", consent, consent, "shared"])
        # The consent keeps the age it had: promoting is not renewing.
        self.assertEqual(
            case["cookies"], [self._shared(ACCEPTED, max_age=FULL_TTL - 10 * DAY)]
        )

    def test_shared_cookie_wins_over_a_conflicting_host_only_one(self):
        case = self._case("promote_shared_wins")
        # Before: both are sent, and the older host-only one shadows the rest.
        self.assertEqual(
            case["results"][2],
            "website_cookies_bar=%s; website_cookies_bar=%s" % (ACCEPTED, REFUSED),
        )
        self.assertEqual(
            case["results"][3:], ["shared-wins", "website_cookies_bar=" + REFUSED]
        )
        self.assertEqual(case["cookies"], [self._shared(REFUSED)])

    def test_nothing_to_promote(self):
        case = self._case("promote_nothing")
        self.assertEqual((case["results"], case["cookies"]), (["none"], []))

    def test_legacy_and_expired_consents_are_not_promoted(self):
        for name in ("promote_legacy", "promote_expired"):
            with self.subTest(case=name):
                case = self._case(name)
                self.assertEqual(case["results"][1], "dropped")
                self.assertEqual(case["cookies"], [])

    def test_consent_without_ts_gets_the_full_lifetime(self):
        case = self._case("promote_without_ts")
        self.assertEqual(case["results"][1], "promoted")
        self.assertEqual(case["cookies"][0]["maxAge"], FULL_TTL)
        self.assertFalse(case["cookies"][0]["hostOnly"])

    def test_rfc_literal_cookie_identity_on_the_bare_domain(self):
        case = self._case("strict_identity_portal")
        self.assertEqual(
            case["results"][1:],
            [
                "promoted",
                "website_cookies_bar=" + REFUSED,
                "shared",
                "website_cookies_bar=" + ACCEPTED,
            ],
        )
        self.assertEqual(case["cookies"], [self._shared(ACCEPTED)])

    def test_consent_survives_a_browser_refusing_the_domain(self):
        case = self._case("browser_refuses_domain")
        self.assertEqual(
            case["results"][1:],
            ["host-only", "host-only", "website_cookies_bar=" + REFUSED, ""],
        )
        self.assertEqual(len(case["cookies"]), 1)
        self.assertTrue(case["cookies"][0]["hostOnly"])
        self.assertEqual(case["cookies"][0]["domain"], "foo.blogspot.com")
