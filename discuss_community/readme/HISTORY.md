## 19.0.1.8.0 (2026-09-30)

- Registered community members get the guest profile. Every community
  behaviour now pivots on `res.users.is_community_member` (the community
  group, never administrators, merchants or zone managers) instead of
  `is_community_guest`:
  - record rules: no staff channels ("general", "Administrators" and any
    channel restricted to employees) nor their messages, only their own
    member rows in channels, the same join restrictions;
  - self-managed for `discuss_channel_zone`: the nightly reconciliation no
    longer undoes the channels a resident joined or left;
  - `session_info.is_community_member` drives the trimmed Discuss UI and the
    landing in "Canarias Conectada"; no Discuss Configuration menu; no
    OdooBot onboarding (`odoobot_state` disabled on promotion); @-mention
    suggestions limited like a guest's;
  - the auto-subscription carve-out exempts administrators, merchants and
    zone managers who also hold the community group.
- Migration: removes the staff-channel seats and OdooBot DMs of every
  community member (`_cleanup_community_members`, formerly guests only).
- Unchanged: the garbage collector only removes guests; moderation keeps
  holding guests and applying the trust threshold to members.
- Zone changes: like guests, a registered member is self-managed, so when
  its zone changes it is seated in the new zone channel but NOT removed
  from the old one (the sync only adds for self-managed users).
- Hardening after review: migrated merchants
  (`group_migrated_merchant`) are exempt too; the member population is one
  SQL search; group-side membership changes (`res.groups` write) refresh
  the cached rule domains; a member's own new channel is created open
  (`group_public_id` unset) so the rule does not hide it; the global
  @-mention and invite searches only offer the people the member already
  shares a chat or group with; every removed seat is logged with its
  login and channel.

## 19.0.1.7.0 (2026-09-29)

- Guests entering from a commercial-zone site are seated in that zone's
  channel again. The arrival zone of a website now reads the company's
  `zone_company_key` ("Zona Comercial Guanarteme" and its siblings) before
  `commercial_zone`, which is `canarias` on those companies, so every guest
  from a zone site landed in the general channel only. A returning guest
  with no neighbourhood adopts the one of the zone site it enters through.
- Community guests see the four community channels in the Channels view
  (general plus the three neighbourhood channels, which are gated on
  `group_zone_channel_member`) and can join and leave each one: new
  non-stored `res.users.community_channel_ids`, read by the guest channel
  and join rules. Staff channels stay hidden and unjoinable, and guests
  still only read their own member row in a channel.
- Guests are self-managed for `discuss_channel_zone`: seated on arrival,
  never unseated by the sync or the nightly reconciliation afterwards.
- Migration: seats the existing guests in the general channel and their
  zone channel when missing (idempotent, adds only).
- The daily guest cleanup now removes every guest inactive for more than
  `discuss_community.guest_inactivity_days` (system parameter, default 7).
  Last activity is the latest of the last login, the last authored message,
  the last presence and the account creation. Channel memberships and push
  devices are deleted; the user is deleted (archived if that fails); the
  partner is deleted, or archived when it authored messages so they stay
  readable. Only `is_community_guest` accounts are touched; counts are
  logged. At most `discuss_community.guest_cleanup_batch_size` (default
  200) guests per run; the cron commits through the `ir.cron` progress API
  and is looped while more remain.
- Security: a guest can no longer seat itself in somebody else's `group`
  conversation (support conversations, private groups) by creating its own
  member row. The guest join rule now allows: open and community channels
  (and their threads), chats it created itself, rows for OTHER people in a group it belongs
  to, and any row in a group it created. Its own support conversation
  (seated with sudo), DMs and being invited by others are unaffected.

## 19.0.1.6.0 (2026-09-26)

- Foreground chime in the backend for the messages core does not sound for
  but the server pushes: every message on a phone-sized screen, and every
  message of a community channel for members without a setting of their
  own. Through core's `_playSound` (the "message sound" switch, main tab
  only, Android left to the push). Core's own "new-message" plays share the
  2-second throttle, so no message rings twice. Only MESSAGE plays are
  throttled: a play tagged with another `ccKind` (a new order) passes, so a
  chat chime can never swallow an order chime.
- `session_info` carries `community_channel_ids`.

## 19.0.1.5.1 (2026-09-26)

- i18n: all .po files regenerated from a fresh export (two missing model
  entries added); test that the banner strings are served to the browser in
  Spanish (`#. odoo-javascript` entries).

## 19.0.1.5.0 (2026-09-25)

- The Discuss notifications banner now VALIDATES instead of reading the
  browser permission: on every Discuss load it asks the server
  (`mail.push.device.cc_push_status`) whether this device's subscription on
  core's backend worker is registered for the current user, and shows
  "Notifications are not active on this device" whenever it is not.
  "Activate and verify" asks for permission (inside the tap, as iOS
  requires), subscribes with the VAPID key, registers the device, re-checks
  it and sends a real test notification (`cc_push_test`). A subscription
  linked to another account is replaced by a fresh one (unsubscribe and
  subscribe again), which proves possession without weakening the
  anti-hijack rule. Denied, unsupported (iOS outside the home-screen app),
  still-linked and server errors each get their own next step. Motivated by
  the 2026-09-26 incident: an iPhone with permission granted and no device
  row on the server.
- Root cause of the 2026-09-26 incident, confirmed in production: device 4
  (Apple endpoint) belonged to partner 6 and was written at 18:55:54, the
  moment of the "guest" registration. The installed iOS app was still logged
  in as that account, so every registration re-confirmed ITS row, silently,
  and nothing was ever stored for the guest. The validating banner makes that
  visible ("linked to another account") and fixes it with a fresh endpoint.
- Community channels ("Canarias Conectada" and the three zone channels) now
  push every PUBLISHED message to every member whose member and user
  notification preferences are both unset (core's default there is
  "mentions only"). Explicit "mentions" / "nothing" choices are kept; no
  member row is written. Held moderated messages push to nobody; they are
  pushed when a moderator approves them, through core `message_post`.
- Fix: Discuss no longer shrinks to its content next to the banner (the
  wrapper row let core's Discuss root take `flex: 0 1 auto`, leaving an empty
  band on the right). Browser tour checks the width with the banner shown and
  hidden, and the member panel for administrators.
- Depends on `mail_push_guest`.

## 19.0.1.4.1 (2026-09-25)

- Tests: the Discuss tours run without a screencast. Discuss keeps repainting
  until Chrome closes, and an acknowledged frame on the closing socket failed
  the test with a BrokenPipeError after the tour had succeeded.

## 19.0.1.4.0 (2026-09-25)

- Discuss guest profile for community guests (`is_community_guest`):
  - they land in the "Canarias Conectada" channel after login;
  - no call, video call, member list or other header actions, no member
    panel and no "Start a meeting" button (OWL patches gated by the
    `is_community_guest` flag of `session_info`);
  - no Discuss "Configuration" menu (filtered in `_visible_menu_ids`, guests
    only);
  - no OdooBot: new guests are born with OdooBot disabled and the first-load
    onboarding is skipped for older ones.
- Global record rules: a guest reads only the channels it is a member of and
  the open public channels, never "general" or "Administrators", and cannot
  join them. Non-guests are untouched.
- Global read rule on channel members: in a `channel` a guest reads only its
  own membership row (no roster of the community channel by RPC); in chats
  and groups it belongs to it reads the other members; nothing in the staff
  channels.
- @-mention suggestions for guests (`get_mention_suggestions_from_channel`):
  core filters by channel membership in raw SQL, past the member rules, so a
  guest could list a whole roster. A guest is now offered only the people
  who posted in a channel (plus itself), or the members of its own chats and
  groups, and at most 8 suggestions per call.
- Changing `is_community_guest` on an existing user clears the registry cache,
  so the cached rule domains follow.
- Migration: existing guests leave "general", "Administrators" and their
  OdooBot chat; OdooBot is disabled for them.
- "Turn on notifications" banner at the top of Discuss for every user until
  the browser permission is granted; hidden for the rest of the session when
  closed, with instructions when the permission was denied.
- Translations in French, German, Italian, Portuguese and Polish; Spanish
  completed.
