# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""A push is written in the language of whoever READS it.

Core builds one payload in the poster's environment and sends it to every
device. The translatable parts of a message push (core's attachment wording,
this module's "%(author)s in %(channel)s", the test push body) therefore
reached a Spanish phone in English whenever the poster's environment was
English. These tests pin one payload per reader language.

CI databases only have en_US: es_ES is activated in the setup. Code
translations are read from the modules' .po files, so nothing else needs
loading.
"""

from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.mail.models import mail_thread

from .common import FCM_ENDPOINT, MailPushGuestMixin


@tagged("post_install", "-at_install")
class TestPushLanguage(MailPushGuestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_ES")
        cls._setup_push_fixtures()
        cls.user_author.lang = "en_US"

        def _user(login, lang):
            return cls.env["res.users"].create(
                {
                    "name": login,
                    "login": login,
                    "email": f"{login}@example.com",
                    "lang": lang,
                    "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
                }
            )

        cls.user_es = _user("mpg_lang_es", "es_ES")
        cls.user_en = _user("mpg_lang_en", "en_US")
        cls.device_es = cls._create_device(
            FCM_ENDPOINT % "lang-es", partner=cls.user_es.partner_id
        )
        cls.device_en = cls._create_device(
            FCM_ENDPOINT % "lang-en", partner=cls.user_en.partner_id
        )
        # A group: every member is a web push recipient, no preference needed.
        cls.group = cls.env["discuss.channel"].create(
            {"name": "Vecinos", "channel_type": "group"}
        )
        cls.group.add_members(
            partner_ids=(
                cls.partner_author + cls.user_es.partner_id + cls.user_en.partner_id
            ).ids,
            post_joined_message=False,
        )

        cls.guest_b.lang = "es_ES"
        cls.guest_author.lang = "en_US"
        cls.device_guest_es = cls._create_device(
            FCM_ENDPOINT % "lang-guest-es", guest=cls.guest_b
        )
        cls.device_guest_en = cls._create_device(
            FCM_ENDPOINT % "lang-guest-en", guest=cls.guest_author
        )

    def _post_attachments_only(self, channel):
        """A message with no text and two files: core writes the body."""
        return (
            channel.with_user(self.user_author)
            .with_context(lang="en_US")
            .sudo()
            .message_post(
                body="",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                attachments=[("a.txt", b"a"), ("b.txt", b"b")],
            )
        )

    def _payload_by_endpoint(self, mocked_push):
        payloads = self._pushed_payloads(mocked_push)
        return dict(zip(self._pushed_endpoints(mocked_push), payloads, strict=True))

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_partner_push_follows_the_recipient_language(self):
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_attachments_only(self.group)
        pushed = self._payload_by_endpoint(mocked_push)
        self.assertEqual(
            pushed[self.device_es.endpoint]["options"]["body"], "a.txt y b.txt"
        )
        self.assertEqual(
            pushed[self.device_en.endpoint]["options"]["body"], "a.txt and b.txt"
        )

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_guest_push_follows_the_guest_language(self):
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_attachments_only(self.channel)
        pushed = self._payload_by_endpoint(mocked_push)
        spanish = pushed[self.device_guest_es.endpoint]
        english = pushed[self.device_guest_en.endpoint]
        self.assertEqual(spanish["title"], "Maria Author en Guanarteme")
        self.assertEqual(spanish["options"]["body"], "a.txt y b.txt")
        self.assertEqual(english["title"], "Maria Author in Guanarteme")
        self.assertEqual(english["options"]["body"], "a.txt and b.txt")

    def test_test_push_is_written_in_the_owner_language(self):
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self.env["mail.push.device"].with_user(self.user_es).with_context(
                lang="en_US"
            ).cc_push_test()
        payload = self._pushed_payloads(mocked_push)[0]
        self.assertEqual(
            payload["options"]["body"],
            "Las notificaciones están activas en este dispositivo ✓",
        )
