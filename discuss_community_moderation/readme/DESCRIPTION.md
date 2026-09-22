Pre-moderation of the `discuss_community` populations — walk-in community
guests and freshly registered community members — on top of the
`discuss_channel_moderation` engine, with the pending state rendered inside
the Discuss client itself.

Phase 2 of the Comunidad move. Phase 1 made residents and walk-in guests
INTERNAL users, and the engine's contract is "internal users are never
held" — so out of the box neither population was moderated at all. This
bridge extends the engine's hold decision, through inheritance and after
`super()`, with two per-channel switches and a probation counter:

- **Moderate Community Guests** (default on): a walk-in guest
  (`is_community_guest`) is held for as long as the switch is on. Guests
  never build up trust — a throwaway account must not be able to buy its way
  out of moderation with three polite messages.
- **Moderate New Community Members** (default on) + **Trust Threshold**
  (default 3): a registered member is held until they have had that many
  messages APPROVED on the channel; from then on they post freely **there**.
  Trust is per channel, per author, and is nothing but a count over the
  engine's own decided rows — an approved `discuss.channel.pending.message`
  already stores who approved it and when.

Everything else is the engine, unchanged: the single hold funnel, the held
payload outside `mail.message`, the quotas, the edit gate (a
below-threshold member's edit of a published message re-enters the queue),
the moderator queue views and the late-moderation escalation.

## The Discuss client finally listens

The engine has always pushed `discuss.channel.moderation/author_status` to
the author's bus; no Discuss client rendered it (its ROADMAP says so). This
module closes that gap for the backend client the community lives in:

- A held post shows up inline at the bottom of the thread as the author's
  own words with a subtle **Pending review** badge — and survives reloads,
  because the channel's store payload carries the CALLER'S OWN pending rows
  (`cc_pending_messages`, never anybody else's).
- On approval the badge disappears and the real message arrives through the
  normal channel notifications.
- On rejection the body stays on screen next to the moderator's reason.
- Core's client would crash on the engine's empty-recordset contract
  (`message_id: false`) and leave the optimistic temporary message on
  screen as if published; a narrow `doMessagePost` patch removes it instead.

Moderators keep the backend list views as their queue; no sidebar badge is
added (see ROADMAP).
