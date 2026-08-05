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
