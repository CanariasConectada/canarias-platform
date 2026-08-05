The community page of the Canarias Conectada app, at `/chat` on the main
website. It is called **Comunidad** everywhere a person sees it: the name says
what is behind the link without promising that somebody is answering right now,
and it still fits once the general channel, the neighbourhood channels and
customer support all live inside it.

A visitor sees the channels they are allowed to open, reads the conversation,
writes in it, and — when their message is held for review — is told so and
invited to create an account. That is the whole of version one. No attachments,
no reactions, no typing indicator, no moderation from the phone.

## How it is reached

One menu entry, injected into `website.navbar_nav` and driven by two booleans
on `website`. The main portal links to its own `/chat`; the three neighbourhood
portals, which are on their own subdomains, link to the portal by absolute URL
built from its stored `domain`. The 214 merchant microsites get nothing — a
shop's window is not a public square.

## Where it sits

- `discuss_channel_zone` seeds the four channels and decides **who may see
  which**. This module never answers that question; it renders the result of a
  `search()` the record rule already filtered.
- `discuss_channel_moderation` decides **whether a message is published**. This
  module renders "en revisión" for its author and reacts to the module's bus
  notifications.
- `website_pwa` provides the app shell. The page is rendered inside
  `website.layout`, so it carries the manifest link and the site's theme.

## Why not core's public Discuss page

`/discuss/channel/<id>` renders `mail.discuss_public_channel_template`: a
standalone `<html>` document with its own `<head>`, no manifest link, no
website header or footer. A visitor tapping "chat" inside the installed app
would step out of the app without being told.

## Why not `im_livechat`

Odoo's Discuss OWL components live in `web.assets_backend`. The one shipped
route to them on the public site is installing `im_livechat`, whose manifest
injects `im_livechat.assets_embed_core` into `web.assets_frontend`.

That was weighed and refused. `im_livechat` is not installed on this platform,
and installing it adds a large bundle to the frontend of **all 218 websites**,
including 217 that have no chat page — a platform-wide asset decision taken to
save code in one module. It would also couple this page to an embed API written
for a support widget: a chatbot-aware, operator-oriented, single-conversation
component set, none of whose assumptions match a public community channel.

What is used instead is the messaging piece core already puts in the frontend
bundle: `bus`. Everything else — the message list, the composer, the held
state — is about three hundred lines in this module, with no new dependency and
no effect on any website that does not enable the chat.

The trade is honest and worth restating: this module owns code Odoo would
otherwise own. It is a message list, a composer and two bus subscriptions, and
it reads messages through core's own `_message_fetch` and posts through core's
own `/mail/message/post`, so the parts that are security-sensitive are still
core's.

## What it does not do

Nothing here assumes push notifications exist. The held state, the approval and
the rejection all arrive over the bus while the page is open, and all three
survive a reload because the server renders them. Web push is
`website_pwa_push`'s business and ships behind its own switch; this page never
asks a visitor for notification permission.
