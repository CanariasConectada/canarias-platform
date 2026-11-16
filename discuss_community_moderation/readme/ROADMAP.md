## Known limits

- **No sidebar badge for moderators.** The engine's `pending_count` could be
  shipped as a per-channel store attr and rendered on the Discuss sidebar,
  but it would need its own moderator-only predicate, an extra template
  patch and a bus refresh path — more surface than the number is worth while
  the backend queue views and the late-moderation email already cover the
  "somebody is waiting" problem. Revisit if moderators actually live inside
  Discuss all day.
- **Trust never decays.** Three approvals end the probation on that channel
  for good; a member who turns sour afterwards is a job for the engine's
  edit gate (their rewrites re-enter the queue only while they are below
  threshold) and for human moderation, not for this counter. Raising the
  channel's threshold above their count puts them back on probation.
- **Text-bearing system notices of moderated personas go through the
  queue.** Same deliberate trade-off as the engine documents for guests:
  "joined the channel" embeds a persona-controlled name, so a
  below-threshold member self-joining a channel produces a held row.
  Contentless notices are still dropped by the engine.
- **Rejections are announced once.** The rejected body and reason are shown
  live over the bus; after a reload only pending rows are replayed into the
  thread. A rejection inbox would need its own read-state model.
