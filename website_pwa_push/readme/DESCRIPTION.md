Adds Web Push to the public website app.

`website_pwa` makes each microsite installable and serves it a service worker.
`mail_push_guest` lets an anonymous visitor own a push subscription and pushes
channel messages to guests. Nothing joined the two: the worker had no `push`
handler, and no page ever asked the visitor for permission.

This module appends the `push`, `notificationclick` and `pushsubscriptionchange`
handlers to the worker — only for websites with `pwa_push_enabled`, a switch
separate from the app switch — and ships the snippet whose button asks for
permission.

The notification a visitor sees carries the author's name and the beginning of
the message, on a screen that may be locked. See the README.

## Two workers, one origin

An origin running the installed app has two service workers: the website's
(`/service-worker.js`, scope `/`, the app's start page) and core's backend one
(`/web/service-worker.js`, scope `/odoo`). A push is handled only by the worker
of the registration that owns the subscription. Core appends its push handler
to the backend worker for internal users only, and the website worker has
push handlers only where `pwa_push_enabled` is on. So internal users are
subscribed on the backend worker, portal users and guests on the website
worker, and the page script decides which (`pushTarget()` in `pwa_push.js`).
