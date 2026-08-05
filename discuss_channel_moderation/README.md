# Discuss Channel Moderation

**Version:** 19.0.1.0.0 | **License:** AGPL-3 | **Author:** Canarias Conectada

Pre-moderation for `discuss.channel`. Content from an untrusted persona (a
guest, optionally a portal user) is HELD — its body, its files, its edits —
until one of the channel's moderators approves it. Reactions and guest display
names are sanitised rather than held; link preview cards are refused outright.
`readme/HISTORY.md` carries the exact table of what is gated and where.

Generic on purpose: the module knows nothing about zones, websites or
companies. It only knows channels, personas and a queue.

**Moderation is for anonymous visitors.** `Moderate Portal Users` is off by
default and self-signup is a click away, so a registered visitor posts straight
through. That is the product decision, not a bug — but it means "moderated
channel" is not a promise that everything on it was reviewed. See
`readme/DESCRIPTION.md` for what the module does and does not guarantee.

See the `readme/` fragments for the full description, usage and roadmap.

## Why the held message is not a `mail.message`

`mail.message` has no `ir.rule` at all. Its access is code-driven in
`mail/models/mail_message.py` and it is *document* scoped: anyone who can read
the channel reads every message of it. There is no per-message visibility
seam, so a "hidden" `mail.message` would still be readable by the very people
it is hidden from. The held payload therefore lives in its own model,
`discuss.channel.pending.message`, and only becomes a `mail.message` on
approval.

## Dependencies

- `mail` (Odoo core)

## Credits

### Contributors

- Mike Colangelo

### License

[AGPL-3](https://www.gnu.org/licenses/agpl-3.0.html)
