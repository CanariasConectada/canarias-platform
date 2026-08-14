Known limits of version one, written down so nobody has to rediscover them.

- **A guest row per anonymous channel visit.** Opening `/chat/<id>` without a
  cookie creates a `mail.guest`, because that is the smallest identity that
  lets the moderation module tell one anonymous author from another. Core has
  the same exposure on `/discuss/channel/<id>`. The page is `sitemap=False`, so
  it is not advertised, but a determined crawler still leaves rows behind. A
  cleanup cron for guests with no message and no membership is the obvious fix.

- **No history.** The page renders the last 30 messages and grows from there.
  There is no "load older messages" button yet.

- **No attachments, reactions or typing indicator.** Deliberate. Every one of
  them is a moderation surface (`discuss_channel_moderation` documents which
  gates exist and why), and adding them without the matching gate would be a
  regression in a module whose whole point is that the gate is not optional.

- **No moderation from the phone.** Moderators approve and reject from the
  backend queue. A moderator arriving at `/chat` sees the page every other
  registered user sees.

- **No unread counter and no membership.** The page reads and posts without
  seating anybody in `discuss.channel.member`, which is all the record rule
  needs for a channel. The consequence is that "how many messages since I last
  looked" cannot be answered yet, and neither can push notifications keyed on
  membership (`mail_push_guest`).

- **Rejection notices are not persistent.** A rejection is shown when it
  arrives on the bus. Reload the page and it is gone, because only `pending`
  rows are rendered by the server. Showing a decided row once, then
  acknowledging it, needs a field the moderation module does not have.

- **No notifications from this page.** Deliberate, and not a gap to be filled
  here: web push belongs to `website_pwa_push` and is switched on separately,
  once the chat has been running for a few days. When it is, the moment worth
  notifying is a moderation decision on the reader's own held message — the bus
  notification this page already listens to.

- **The menu entry is not editable from the website builder.** It is QWeb
  driven by two booleans rather than a `website.menu` row, which is what makes
  it correct on 218 sites with nothing to migrate; the price is that an
  administrator cannot rename or reorder it from the editor. Turning it into a
  real menu record is a fair future ask, and would need a hook that creates one
  row per website that has the flag.
