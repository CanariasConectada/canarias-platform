**Comunidad** in the site menu opens `/chat`, which lists the channels the
visitor may open. `/chat/<id>` is one channel:
the conversation, a composer, and — for the person who wrote it and nobody
else — anything of theirs still waiting for review.

## What a visitor without an account sees

They can read and write in the general channel. Their first message does not
appear: it goes to the moderation queue, and the page tells them so and offers
them an account. The three neighbourhood channels are not on their list at all,
because the record rule filters them out of the search — they are not shown a
link that would 404.

## What a registered user sees

All four channels, and their messages publish immediately (unless a moderator
has turned on **Moderate Portal Users** for that channel).

## Live behaviour

New messages arrive over the bus without reloading. When a moderator approves
or rejects a held message, its author is told on the spot, with the rejection
reason if one was given. Everything survives a reload: the held state is
rendered by the server, not held in the browser.

## Deep links

`/chat/12` is the twelfth channel. The id rather than a slug, because the
channels are renameable from the Discuss UI and a slug would rot on the first
rename. `mail`'s own `/chat/<token>` routes are untouched: werkzeug matches the
numeric segment against the `int` rule and everything else against core's.

## Asking for support from Discuss

Merchants, walk-in community guests and any other internal user who is not a
support agent find a **Request support** button at the top of the Discuss
sidebar. It opens their support conversation, the same one the website button
opens for their account, with the same agents seated, or reopens it if it
was closed. Agents and administrators do not see the button, and the route
behind it refuses them.

## Who is asking

A support conversation is named `Soporte · <name>`, cut at 64 characters,
so an agent can see who is asking in the Soporte drawer and in the thread
header. The name is the one the visitor typed on the identify card, or else
the account's name, or else the guest's. Walk-in community guests are
accounts named "Invitado …", so they are shown the identify card as well.
