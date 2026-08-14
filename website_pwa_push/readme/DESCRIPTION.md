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
