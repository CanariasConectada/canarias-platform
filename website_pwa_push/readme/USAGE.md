## 1. Have a VAPID key pair

Push is silent without it, on both sides. The pair lives in
`ir.config_parameter` as `mail.web_push_vapid_private_key` and
`mail.web_push_vapid_public_key`; `mail_push_guest`'s USAGE explains how it is
generated and why it must be treated as immutable once published.

## 2. Turn it on for one website

Website → Settings → *App instalable (PWA)*:

- **Instalable como app** (`pwa_enabled`) — required. The push handlers live
  inside the service worker, which is not served at all without it.
- **Avisos push** (`pwa_push_enabled`) — the switch this module adds.

Every other website is untouched: its `/service-worker.js` keeps serving the
exact bytes it served before this module was installed.

## 3. Put the button on a page

Edit any page → drop the **Activar avisos** snippet. It is a snippet rather
than a fixed block for the same reason `website_pwa`'s install card is: the
right place is not the same on a marketplace, on a zone portal and on a
merchant microsite.

The card is hidden until the script decides which of its branches is honest for
this browser (see the table in the README). On a website without push, or in a
browser without `PushManager`, it stays hidden entirely.

## 4. What the visitor does

Clicks the button → the browser asks → on "allow", the browser subscribes and
the subscription is POSTed to `/mail/push/subscribe`, bound to whoever the
session is: the `dgid` guest cookie, or the logged-in user. A visitor with
neither gets a 404 from that route and no subscription, by design — a device
bound to the shared public partner would be one where everybody's messages
arrive.

From then on, a message posted to a `discuss.channel` they are a member of
reaches the phone, with the rules `mail_push_guest` documents (never the author,
never a muted member, never one who turned notifications off).

## Sending a test push

There is no button for it. From a shell, post a message to a channel the test
browser is a member of:

```python
channel = env["discuss.channel"].browse(CHANNEL_ID)
channel.message_post(body="Prueba de aviso", message_type="comment")
```

If nothing arrives, check in this order: the VAPID parameters exist; the device
row exists (`mail.push.device` with the expected `guest_id` or `partner_id`);
the website has both switches on; `/service-worker.js` contains
`addEventListener("push"`; and the browser's own notification settings for the
site.
