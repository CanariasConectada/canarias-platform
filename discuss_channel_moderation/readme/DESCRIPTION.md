Pre-moderation of `discuss.channel` content posted by untrusted personas.

When a channel has an active moderation configuration, anything posted by a
guest — and optionally by a logged-in portal user — never becomes a
`mail.message`. It is stored as a `discuss.channel.pending.message` row that
only the moderators of that channel can see, and it is published (as a real
comment, still attributed to its original author) when a moderator approves
it. Rejected messages are never published and their reason is pushed back to
the author over the bus.

## What the module guarantees

On a channel with an active configuration, and for a persona that
configuration holds (guests always, portal users only when **Moderate Portal
Users** is on), no content from that persona reaches a third party before a
moderator approves it:

- **Message bodies.** Held outside `mail.message` entirely, whatever
  `message_type` the caller claims to be posting.
- **Attachments.** An upload aimed at a moderated channel never becomes a
  channel attachment: it is deferred on `create`, then parented to the held
  row, where the attachment's own ACL check resolves to "can this user read
  that held message?". `/discuss/channel/attachments` cannot serve what is not
  there. The moderator can open it, because it is the evidence they decide on.
- **Edits of an already published message.** An untrusted edit withdraws the
  published message and puts the new content back in the queue, so being
  approved once is not a licence to publish anything afterwards.
- **Reactions.** On the untrusted path a reaction must have the shape of a
  single emoji; core accepts any string, at any length.
- **Guest display names.** Markup stripped and length capped, on creation and
  on rename, because a byline is served to third parties exactly like the
  message under it.
- **Link preview cards.** Refused outright on a moderated channel — see below
  for why this one is not a persona rule.
- **The evidence of a held message.** Its author keeps the ownership token the
  upload route handed them, so `/mail/attachment/delete` would let them destroy
  the file the moderator is being asked to judge. Only internal users can
  delete or re-parent a held attachment.
- **Sub-channels.** A thread opened under a moderated channel inherits its
  parent's configuration and feeds the parent's queue.

## What it does NOT guarantee

- **A portal account escapes moderation, by design.** `Moderate Portal Users`
  is OFF by default and the platform allows self-signup, so registering is
  precisely how a visitor stops being moderated. "Moderated channel" therefore
  means "moderated for anonymous visitors" until that switch is turned on — it
  is not a promise that everything on the channel was reviewed.
- **No rate limiting.** There is a ceiling on the size of a held body and on
  how many held rows one persona may leave on one channel, and that is all.
  See ROADMAP.
- **Internal users are never held**, moderators included.
- **Nothing outside `discuss.channel`.** The module moderates the channels it
  was pointed at; the one exception is the guest name, which follows the
  persona everywhere and is sanitised for every guest.
- **Nothing about channel metadata.** The channel's own name, avatar and
  description are writable only by users who hold write access on
  `discuss.channel`; `base.group_public` and `base.group_portal` are read-only
  there (`mail/security/ir.model.access.csv:13-14`), so no untrusted persona
  can reach them and this module adds no gate.
- **No rich link cards on a moderated channel**, for anybody. That is the cost
  of the preview rule, not an oversight.

## Design constraints

- **The hold lives on the model, never on a route.** Gates sit on
  `discuss.channel.message_post`, `discuss.channel._message_update_content`,
  `ir.attachment.create`, `ir.attachment.write`/`unlink`,
  `mail.message._message_reaction`, `mail.guest.create`/`_update_name`,
  `mail.link.preview._create_from_message_and_notify` and
  `mail.message.link.preview.create`. A new route, a new widget or a raw RPC
  call cannot route around them.
- **The list above is the guarantee, and it is not "every funnel".** An earlier
  version of this file said the module covered every funnel that reaches a
  third party. Three rounds of adversarial validation falsified that sentence
  three times. What is claimed now is exactly the list, and what is deliberately
  not on it is written down (see HISTORY and ROADMAP) so the next review can
  start from the gaps instead of rediscovering them.
- **No bypass is keyed on the context.** The public post route runs
  `request.update_context(**context)`, so every context key is
  attacker-controlled; a context-keyed exception would be forgeable by the
  personas being moderated.
- **The persona decides, never the payload.** `message_type` is part of
  `_get_allowed_message_params` and is forwarded verbatim from `post_data` on
  the `auth="public"` route, so it is attacker-chosen. An untrusted author is
  held whatever their message claims to be, and approval always publishes a
  plain `comment` — the type they sent is never stored and never reused.
  Two deliberate departures, each with its reason written at the code:
  **link previews** ask a channel question, because a per-caller rule cannot
  hold when the preview cache is keyed globally by URL and the content can
  change after approval; and the **contentless system notice** is recognised by
  its body, which is safe only because the branch it selects publishes nothing —
  a forger can use it to discard their own post, never to publish one.

Security is two groups under a single privilege — Moderator and Administrator
— plus record rules scoping each moderator to the queues of the channels they
were explicitly listed on. Nothing is granted to `base.group_public` or
`base.group_portal`.
