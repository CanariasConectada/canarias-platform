## 19.0.2.0.0 (2026-09-25)

Push was not reaching the installed app. Root cause and evidence are in
DESCRIPTION.md ("Two workers, one origin"). Changes:

- Subscriptions go to the worker that will handle them: internal users are
  subscribed on core's backend worker (`/web/service-worker.js`, scope
  `/odoo`, the only one with core's push handler), even from a website page
  and whatever the website push switch says; portal users and guests stay on
  the website worker; an anonymous visitor on the login page grants
  permission and core subscribes right after the login.
- New in-app prompt for signed-in users: shown only inside the installed app
  while permission is undecided, with a "Turn on notifications" button (iOS
  only asks from a tap) and a "Not now" that is remembered on the device.
- New `website_pwa_push.pwa_notify_card` template, shared by the prompt, the
  login page block and any other page.
- A tapped notification now opens the conversation when the app is showing
  the website: core's worker posts `OPEN_CHANNEL` to the open window and
  relies on a Discuss client being there to act on it; the website had no
  listener.
- iOS outside the installed app now gets the "install first" hint: the push
  support check ran first and is always false in Safari tabs on iOS, so the
  hint was unreachable.
- A subscription made with a rotated VAPID key is replaced instead of being
  registered as a device nothing can encrypt for.
- No double notifications: after subscribing an internal user on the backend
  worker, the browser's subscription on the website worker (if any) is
  unsubscribed and its row removed through `/mail/push/unsubscribe`. The
  subscribe call now sends `worker` so `mail_push_guest` can record it and
  drop leftovers server side.
- `whenActive` rejects with a clear error (and a distinct warning) when the
  registration has no worker at all, instead of waiting forever.
- The page scripts no longer throw when the Push API accessors are missing or
  throw (privacy modes, in-app browsers): the login page keeps working.
- `test_page_script_js.py` executes `pwa_push.js` in node against fake
  registrations, PushManager and worker states.
