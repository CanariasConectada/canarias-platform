# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Two registrations of the same endpoint at once must not be an error.

Client report of 2026-09-29: "El punto de conexión debe ser único" when the
Discuss banner's `/mail/push/subscribe` and core's `register_devices` (woken
by the same permission grant) both INSERT the same endpoint. See
`mail.push.device._cc_endpoint_race_guard`.

Two shapes of the race are exercised:

* VISIBLE: the conflicting row is in this transaction's snapshot but the
  door's own search missed it (simulated by patching `search`). The door must
  fall back to the ordinary "existing row" path, ownership rule included.
* CONCURRENT: the conflicting row was committed by another transaction after
  this one's snapshot was taken (a real second cursor), so no read can see
  it. The door must raise `ConcurrencyError`, which is what makes
  `odoo.service.model.retrying` replay the HTTP request instead of turning
  the unique violation into a ValidationError.
"""

import json
from contextlib import contextmanager
from unittest.mock import patch

from odoo.exceptions import ConcurrencyError
from odoo.sql_db import db_connect
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.mail_push_guest.models.mail_push_device import WORKER_BACKEND

from .common import BROWSER_KEYS, FCM_ENDPOINT, MailPushGuestMixin


@tagged("post_install", "-at_install")
class TestPushEndpointRace(MailPushGuestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_push_fixtures()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _search_misses(self, endpoint, times):
        """The first `times` searches for `endpoint` find nothing.

        That is what the loser of the race sees: its search ran before the
        winner's INSERT, so it goes on to INSERT too.
        """
        model_class = type(self.env["mail.push.device"])
        original = model_class.search
        missed = []

        def search(records, domain, *args, **kwargs):
            if len(missed) < times and [tuple(leaf) for leaf in domain] == [
                ("endpoint", "=", endpoint)
            ]:
                missed.append(domain)
                return records.browse()
            return original(records, domain, *args, **kwargs)

        with patch.object(model_class, "search", search):
            yield missed
        self.assertEqual(len(missed), times, "the patched search was not reached")

    @contextmanager
    def _committed_by_another_transaction(self, endpoint):
        """Commit a row for `endpoint` from a second connection.

        This transaction's REPEATABLE READ snapshot was taken long before, so
        the row is invisible to it while still blocking its INSERT: exactly
        the loser's position in production. The row is removed afterwards.
        """
        with db_connect(self.env.cr.dbname).cursor() as other:
            other.execute("SET LOCAL lock_timeout = '5s'")
            other.execute(
                "SELECT res_id FROM ir_model_data "
                "WHERE module = 'base' AND name = 'partner_admin'"
            )
            partner_id = other.fetchone()[0]
            other.execute(
                "INSERT INTO mail_push_device (partner_id, endpoint, keys) "
                "VALUES (%s, %s, %s)",
                [partner_id, endpoint, json.dumps(BROWSER_KEYS)],
            )
            other.commit()
        try:
            yield
        finally:
            with db_connect(self.env.cr.dbname).cursor() as other:
                other.execute(
                    "DELETE FROM mail_push_device WHERE endpoint = %s", [endpoint]
                )
                other.commit()

    def _register_guest(self, guest, endpoint):
        return self.Device._register_for_persona(
            guest=guest,
            endpoint=endpoint,
            keys=BROWSER_KEYS,
            vapid_public_key=self.vapid_public_key,
        )

    def _rows(self, endpoint):
        return self.Device.sudo().search([("endpoint", "=", endpoint)])

    # ------------------------------------------------------------------
    # Visible race
    #
    # `odoo.sql_db` logs the losing INSERT as a "bad query" at ERROR, as it
    # does for every failed statement; muted, since it is the point here.
    # ------------------------------------------------------------------

    @mute_logger("odoo.sql_db")
    def test_public_door_same_persona_race_is_a_success(self):
        """Losing to our own persona's row: no exception, one row, ours."""
        endpoint = FCM_ENDPOINT % "race-same-guest"
        self._create_device(endpoint, guest=self.guest_b)
        with self._search_misses(endpoint, times=1):
            device = self._register_guest(self.guest_b, endpoint)
        rows = self._rows(endpoint)
        self.assertEqual(len(rows), 1)
        self.assertEqual(device, rows)
        self.assertEqual(rows.guest_id, self.guest_b)

    @mute_logger("odoo.sql_db")
    def test_public_door_other_persona_race_is_still_refused(self):
        """Losing to somebody else's row: the same silent refusal as always."""
        endpoint = FCM_ENDPOINT % "race-other-guest"
        self._create_device(endpoint, guest=self.guest_b)
        with self._search_misses(endpoint, times=1):
            device = self._register_guest(self.guest_outsider, endpoint)
        self.assertFalse(device, "the row of another persona was handed over")
        rows = self._rows(endpoint)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.guest_id, self.guest_b)

    @mute_logger("odoo.sql_db")
    def test_core_door_same_partner_race_is_a_success(self):
        """`register_devices` wraps core's create the same way.

        Two misses: this module's search, then core's own.
        """
        endpoint = FCM_ENDPOINT % "race-core-same"
        self._create_device(endpoint, partner=self.partner_author)
        with self._search_misses(endpoint, times=2):
            self.Device.with_user(self.user_author).register_devices(
                endpoint=endpoint,
                keys=BROWSER_KEYS,
                vapid_public_key=self.vapid_public_key,
            )
        rows = self._rows(endpoint)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.partner_id, self.partner_author)
        self.assertEqual(rows.cc_worker, WORKER_BACKEND)

    @mute_logger("odoo.sql_db")
    def test_core_door_other_persona_race_is_still_refused(self):
        endpoint = FCM_ENDPOINT % "race-core-other"
        self._create_device(endpoint, guest=self.guest_b)
        with self._search_misses(endpoint, times=2):
            self.Device.with_user(self.user_author).register_devices(
                endpoint=endpoint,
                keys=BROWSER_KEYS,
                vapid_public_key=self.vapid_public_key,
            )
        rows = self._rows(endpoint)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.guest_id, self.guest_b)
        self.assertFalse(rows.partner_id)

    # ------------------------------------------------------------------
    # Concurrent race
    # ------------------------------------------------------------------

    @mute_logger("odoo.sql_db")
    def test_public_door_concurrent_race_asks_for_a_retry(self):
        endpoint = FCM_ENDPOINT % "race-concurrent-public"
        with self._committed_by_another_transaction(endpoint):
            with self.assertRaises(ConcurrencyError):
                self._register_guest(self.guest_b, endpoint)
            # The savepoint kept this transaction usable.
            self.assertFalse(self._rows(endpoint))

    @mute_logger("odoo.sql_db")
    def test_core_door_concurrent_race_asks_for_a_retry(self):
        endpoint = FCM_ENDPOINT % "race-concurrent-core"
        with self._committed_by_another_transaction(endpoint):
            with self.assertRaises(ConcurrencyError):
                self.Device.with_user(self.user_author).register_devices(
                    endpoint=endpoint,
                    keys=BROWSER_KEYS,
                    vapid_public_key=self.vapid_public_key,
                )
            self.assertFalse(self._rows(endpoint))
