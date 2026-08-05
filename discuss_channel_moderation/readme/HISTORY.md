## 19.0.1.1.0 (2026-08-05)

- **Late-moderation alert.** A held message that nobody has reviewed after 30
  minutes now emails the moderators of its channel. The in-Odoo counter and the
  bus ping only reach a moderator who is already looking; the visitor who waits
  forty minutes to see their own comment appear is the one who does not come
  back, and neither of those reaches the moderator who went home.
- The delay lives in the system parameter
  `discuss_channel_moderation.late_alert_minutes` (default 30). It is a
  platform-wide promise, not a per-channel setting: a per-channel field would
  let one channel quietly opt out of the SLA the rest of the site advertises.
- **One mail per channel, one mail per message, ever.** Six overdue comments on
  one channel are one email with six lines. A row that has been announced is
  stamped with `late_alert_date` and never enters another email; what keeps a
  busy channel audible is that every NEW message earns its own first alert.
- A moderated channel with no moderator (or with no moderator holding an email
  address) sends nothing and logs a warning NAMING the channel. It is the state
  the alert exists to prevent, so it cannot be the state it fails silently on.
- **The alert proves the mail left before it stamps anything.** A `mail.mail`
  whose recipients resolve to nothing raises no exception at all -- core marks
  it `exception` / `mail_email_missing`, loops over an empty recipient list and
  returns cleanly -- so `raise_exception=True` alone let a send that delivered
  nothing pass for a send. The cron now reads the state of the `mail.mail` it
  created and treats anything but `sent` as a failure, with its own ERROR line
  ("DELIVERED NOTHING") naming the channel, the state and the failure type.
  That is the third distinct way to reach nobody, and it is fixed in a third
  place: not by assigning a moderator, not by filling in an address, but by
  repairing the template or the outgoing mail configuration.
- The template ships `use_default_to="False"`. With the field left at its
  default the alert evaluated no recipient expression at all and every mail
  died as `mail_email_missing`: the feature sent nothing, anywhere, and marked
  every row as announced while doing it.
- A delivery failure is logged with its traceback and leaves the row unflagged,
  so the next run retries it. `raise_exception=True` is still there for the
  failures that do raise: this deployment has had hundreds of mails sit unsent
  with nobody noticing, and an escalation that joins that pile reads as covered
  when it is not.
- Nothing is logged on the happy path. There is no log rotation here.
- The email carries the author and the wait, never the held body: that text is
  precisely what nobody has approved yet.
- No migration ships with this version. The only schema change is a new nullable
  `late_alert_date` on `discuss.channel.pending.message`, and NULL already means
  "never announced" — which is true of every pre-existing row. Rows that are
  already overdue at upgrade time get their first alert on the next cron run,
  batched per channel, which is the intended behaviour and not a repair.
  The mail template is new in this same unreleased version, so `noupdate="1"`
  has nothing to overwrite: a fresh install writes `use_default_to = False`
  itself. Only a database that installed an intermediate build of 19.0.1.1.0
  keeps the broken record, and it is one field on one row in Settings >
  Technical > Email > Email Templates — not worth a migration script.

## 19.0.1.0.0 (2026-08-05)

- First release: per-channel pre-moderation of guest and portal comments,
  held outside `mail.message`, with a scoped backend queue, approval/rejection
  actions and bus notifications for authors and moderators.
- The hold does **not** live on `message_post` alone, and this file no longer
  says it covers "every funnel". `message_post` is the one funnel that CREATES
  a `mail.message`, but reaching a third party does not require creating one:
  three rounds of adversarial validation on a copy of production found three
  separate surfaces that never touch it. What the module carries is a list, and
  keeping the list honest is the maintenance obligation. Gated today:

  | Surface reaching a third party | Gate | Question it asks |
  | --- | --- | --- |
  | Message body | `discuss.channel.message_post` | persona |
  | Edit of a published message | `discuss.channel._message_update_content` | persona |
  | Uploaded file | `ir.attachment.create` | persona |
  | Held file, deleted or re-parented | `ir.attachment.write` / `unlink` | internal only |
  | Reaction content | `mail.message._message_reaction` | persona |
  | Guest display name | `mail.guest.create` / `_update_name` | every guest |
  | Link preview card | `mail.link.preview._create_from_message_and_notify`, `mail.message.link.preview.create` | channel |

- Held bodies (64 KB) and outstanding held rows per persona (20) are capped.
- Moderation is INHERITED BY SUB-CHANNELS: a thread opened under a moderated
  channel is held by the parent's configuration and lands in the parent's
  queue. A sub-channel copies its parent's `group_public_id`, so without this
  the same visitors held upstairs could post freely downstairs.
- Contentless system notices — the "call started" markup core posts when a
  guest joins a call — are DISCARDED instead of queued: approving one publishes
  a stale event, and letting them accumulate burns the per-persona quota
  reserved for text a human has to read.
- Link previews are refused on a moderated channel for EVERYONE, not only for
  untrusted personas. A preview is not reviewable content: `og_image` is stored
  as a URL and re-fetched by every reader's browser on every view, so no
  approval can bind it. Cost: no rich cards on moderated channels; the link
  itself still renders. Benefit: the SSRF in `get_link_preview_from_url` is
  unreachable there too.
- EXPLICITLY OUT OF SCOPE, and not defects: anything outside `discuss.channel`;
  internal users, moderators included; portal users while `moderate_portal` is
  off; rate limiting; and channel metadata (name, avatar, description), which
  needs write access on the channel that no untrusted persona holds
  (`mail/security/ir.model.access.csv:13-14`).
