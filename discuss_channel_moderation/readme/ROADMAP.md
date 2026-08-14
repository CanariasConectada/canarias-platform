## Known limits of the guarantee

- **The late-moderation alert fires ONCE per held message and never escalates
  further.** A channel with one message stuck on it is announced once and then
  goes quiet; only a NEW message earns a new alert. That is the deliberate
  trade-off — re-alerting every five minutes teaches the moderator to filter the
  sender, and the alert would then be loudest exactly when it stops being read —
  but it does mean the module cannot tell the difference between "handled" and
  "ignored forever". The escalation ladder that would (alert the manager after
  two hours, page somebody after four) is an on-call feature with an on-call
  rota behind it, not a mail template, and it does not belong here. What covers
  the worst case meanwhile is the warning logged for a moderated channel with no
  reachable moderator.
- **The alert measures `create_date`, not "unread".** A moderator who opened the
  queue, read everything and decided nothing still gets the mail. Distinguishing
  "seen" from "acted on" would need per-moderator read tracking on a model that
  is deliberately history-only.
- **The cron's own period is added to the threshold.** It runs every five
  minutes, so a 30-minute SLA alerts somewhere between 30 and 35 minutes.
  Lowering the parameter below the cron interval does not make the alert faster.

- **A portal account is the documented way out of moderation.**
  `moderate_portal` defaults to False and the platform has self-signup enabled,
  so a visitor who registers posts straight through. This is intended, not an
  oversight: it is the product decision, and the front-end is meant to say so.
  It does mean "this channel is moderated" is only true for anonymous visitors
  until the switch is turned on.
- **No rate limiting.** A held body is capped (64 KB) and one persona may leave
  at most 20 undecided rows on one channel, but there is no per-IP or
  per-minute limit and no dedupe: the same persona can keep posting as fast as
  a moderator empties the queue. Real rate limiting needs a store shared by all
  workers (Redis, or a table with its own lock discipline) and a decision about
  what to do behind a reverse proxy, which is why it is not in this module.
- **The cookie-less visitor shares one bucket.** A post with no guest cookie is
  attributed to the single public partner, so the outstanding-rows cap is
  shared by every anonymous session on that channel. It is scoped per channel
  for exactly that reason: a platform-wide count would let one flooder lock
  anonymous posting everywhere.
- **Attachment VISIBILITY is enforced, attachment LIFECYCLE is not.** Files of
  a rejected message, and files uploaded by a visitor who never posts, are
  parked out of reach of the public routes but never garbage-collected. (The
  previous version of this file mentioned the lifecycle and never mentioned
  visibility, which is precisely the gap that shipped: an uploaded file was
  listed and downloadable by anonymous visitors without any message existing.)
- **A withdrawn message leaves an empty bubble.** Holding an edit unpublishes
  the original the way core unpublishes a deleted message (empty body), so
  readers see a removed message rather than the message silently reverting to
  its previous text. Approving the edit posts a NEW message; it does not
  resurrect the old row.
- **The guest name guard applies to every guest RENAME and every guest
  CREATION**, not only to guests of a moderated channel, because a rename can
  legitimately happen before joining anything and scoping it would only add an
  ordering trick around it. Names are truncated to 64 characters and stripped
  of markup, where core allows 512 characters of anything. (The previous
  version of this file said "every guest" while the guard only sat on
  `_update_name`, i.e. on renames. Creation goes through `_get_or_create_guest`
  → `create`, which was unguarded. In plain `mail` that path only ever receives
  a constant (`"Guest"`) or an email out of a server-signed token, so nothing
  attacker-controlled reached it; `im_livechat`, which is not installed today
  but will be, passes the visitor's own typed name to the same method. The
  guard now sits on `mail.guest.create`.)

## Missing features

- No JS client is shipped. The bus notifications documented in USAGE are
  emitted, but the Discuss front-end does not yet render a "pending" bubble,
  the rejection reason, or a "your edit is waiting for review" state; today the
  author only learns the outcome when the message appears (or does not).
- Only the moderatable payload survives the hold: body, attachments and
  parent. `subject`, mentions (`partner_ids`) and `special_mentions` passed to
  `message_post` are dropped, so an approved message loses them. Channels
  rarely use `subject`, but mentions are a real gap.
- No auto-moderation: there is no allow/ban list per author, no forbidden-word
  screening and no auto-approval after N accepted messages. `mail_group` has
  the first two (`mail.group.moderation`) and they would port cleanly.
- A message held for a channel whose configuration is later archived stays in
  the queue and still needs a decision; it is not auto-approved.
- An upload sent WITHOUT `is_pending` on a moderated channel is deferred like
  any other, and the current Discuss composer always sets that flag, so this is
  invisible in practice. A future client uploading outside a composer would get
  an attachment with no thread in the upload response.

## Known limits, second pass (after round three)

- **No link previews at all on a moderated channel**, moderators included. The
  card is refused per CHANNEL and not per persona, which is the one place the
  module does not ask the persona question — `models/mail_link_preview.py`
  gives the three reasons. What is lost is decoration: the anchor still renders
  and still works. What is gained is that "a human approved everything a reader
  is served here" stays true even though `og_image` is a live URL the
  publisher can repoint after the approval.
- **The SSRF in `get_link_preview_from_url` is only unreachable on moderated
  channels.** `mail/tools/link_preview.py:10-37` does a `requests.get` with
  `allow_redirects=True` and no host or IP filtering, on a URL an untrusted
  persona chose. This module refuses to start that fetch for a moderated
  channel; on every other channel the hole is core's and is untouched here.
  Fixing it properly (an allow/deny list of resolved IPs, no redirects to a
  different host) belongs upstream, not in a moderation addon.
- **The evidence of a DECIDED row cannot be deleted by its author either.**
  The guard is "internal users only" and does not read the row's state, on
  purpose: reading it would let an archived configuration silently re-open the
  deletion of files already in the queue. A rejected message's file is the
  record of what was rejected, and rows here are history.
- **A held attachment cannot be touched by its author at all** — not renamed,
  not replaced, not removed. An author who wants to withdraw a held message can
  still do so through the ordinary empty-body edit; the file is then parked,
  not published.
- **Contentless system notices are dropped, text-bearing ones are not.** A
  guest joining or leaving a channel still queues a row, because that notice
  embeds a persona-controlled name. Repeated join/leave is therefore still a
  way to fill a queue, which is the rate-limiting gap above, not a new one.
- **Sub-channel inheritance walks exactly one level**, because core allows
  exactly one (`_constraint_parent_channel_id`,
  `mail/models/discuss/discuss_channel.py:151-159`). A row on the sub-channel
  itself wins over the parent's, so a thread can be given its own moderators or
  exempted on its own.
