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
- Changing `is_community_guest` on an existing user clears the registry cache,
  so the cached rule domains follow.
- Migration: existing guests leave "general", "Administrators" and their
  OdooBot chat; OdooBot is disabled for them.
- "Turn on notifications" banner at the top of Discuss for every user until
  the browser permission is granted; hidden for the rest of the session when
  closed, with instructions when the permission was denied.
- Translations in French, German, Italian, Portuguese and Polish; Spanish
  completed.
