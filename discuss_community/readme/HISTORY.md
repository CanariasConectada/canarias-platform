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
