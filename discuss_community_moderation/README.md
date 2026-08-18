# Discuss Community Moderation

Phase 2 of the Comunidad move: pre-moderation of walk-in community guests
and NEW community members, with the pending state rendered inside the
Discuss client.

Phase 1 (`discuss_community`) made both populations INTERNAL users, and the
`discuss_channel_moderation` engine deliberately never holds internal users
— so neither was moderated at all. This bridge extends the engine's hold
decision (via inheritance, after `super()`; the engine's semantics are
untouched) with:

| Switch (per channel) | Default | Effect |
| --- | --- | --- |
| Moderate Community Guests | on | `is_community_guest` accounts are always held; guests never earn trust |
| Moderate New Community Members | on | members are held until **Trust Threshold** approvals on the channel |
| Trust Threshold | 3 | approved held messages needed to post freely on THAT channel; 0 disables the probation |

Trust is a count of the author's APPROVED `discuss.channel.pending.message`
rows on the channel — the engine's decided rows already carry moderator and
date, so no new bookkeeping exists. Per channel, per author, evaluated at
post time against the current threshold.

## Client side (`web.assets_backend`)

- The author's own held messages render inline at the bottom of the thread
  with a **Pending review** badge, and survive reloads: the channel's store
  payload ships the caller's own pending rows (`cc_pending_messages`),
  scoped by `_get_current_persona()` so no other persona's rows can travel.
- The engine's `discuss.channel.moderation/author_status` bus notification
  — emitted since day one, rendered by nobody until now — updates the
  placeholder live: approved removes it (the real message arrives through
  normal channels), rejected shows the reason next to the body.
- A narrow `doMessagePost` patch honours the engine's empty-recordset
  contract (`message_id: false`): the optimistic temporary message is
  removed instead of crashing core's reconciliation and lying on screen.

Existing moderation rows (the seeded zone channels included) get the new
switches on install through plain ORM column initialisation — no XML
override, no post_init hook, `noupdate` untouched. See `readme/` for
usage and known limits.
