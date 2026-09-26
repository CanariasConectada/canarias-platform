# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

# Short-pause-short buzz. Honoured on Android; every other platform ignores the
# key, which is harmless.
PUSH_VIBRATE_PATTERN = [120, 60, 120]


def make_push_payload_audible(payload):
    """Return a copy of ``payload`` that the phone never delivers silently.

    Browsers do not let a web push choose its sound (the Notification API's
    ``sound`` option is unsupported everywhere), so the only thing the server
    controls is that the phone plays ITS OWN notification sound. Two things
    make a notification arrive silently:

    - ``silent: true``, which nothing here sets, but a payload could;
    - a ``tag`` without ``renotify``: the notification REPLACES the previous
      one with the same tag, and the replacement is shown without sound or
      vibration. Both workers group a conversation under one tag, so without
      ``renotify`` only the first message of a burst was ever heard.

    ``renotify`` is set only when a tag is present: ``renotify`` with no tag
    makes ``showNotification`` reject, and core's backend worker has no
    fallback for a rejection -- the push would show nothing at all.

    Idempotent, and never mutates its argument.
    """
    if not isinstance(payload, dict):
        return payload
    options = dict(payload.get("options") or {})
    options["silent"] = False
    options.setdefault("vibrate", list(PUSH_VIBRATE_PATTERN))
    if options.get("tag"):
        options["renotify"] = True
    else:
        options.pop("renotify", None)
    return dict(payload, options=options)


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def _web_push_truncate_payload(self, payload):
        """Add the audible options BEFORE core measures the payload.

        Truncation fits the body to the 4 KB encrypted-record limit, computed
        on the whole JSON. Adding keys after it could push a message that was
        cut to the limit over it, and the push service answers 413.
        """
        return super()._web_push_truncate_payload(make_push_payload_audible(payload))

    def _web_push_send_notification(
        self, devices, private_key, public_key, payload_by_lang=None, payload=None
    ):
        """The single door every web push of the database goes through.

        Catches the payloads that never pass through truncation (core's call
        invitations, `cc_push_test`). For the ones that did, this is a no-op.
        """
        if payload is not None:
            payload = make_push_payload_audible(payload)
        if payload_by_lang:
            payload_by_lang = {
                lang: make_push_payload_audible(lang_payload)
                for lang, lang_payload in payload_by_lang.items()
            }
        return super()._web_push_send_notification(
            devices,
            private_key,
            public_key,
            payload_by_lang=payload_by_lang,
            payload=payload,
        )
