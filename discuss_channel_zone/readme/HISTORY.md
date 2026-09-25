## 19.0.1.1.0 (2026-09-25)

- Channel `name` and `description` are translatable. The ORM converts both
  columns to `jsonb` on upgrade (existing values kept as `en_US`); the
  migration strips the XML indentation from the four seeded descriptions and
  copies every other channel's text to `es_ES`.
- Translations of the four seeded channels and of every UI string of the
  module in Spanish, French, German, Italian, Portuguese and Polish.

## 19.0.1.0.0 (2026-08-04)

- First release: four seeded channels, the `Community Chat: Registered Member`
  group that closes the neighbourhood channels to visitors, `res.users.chat_zone`,
  the idempotent membership sync with its create/write/company triggers, the
  nightly reconciliation cron and the initial `post_init_hook` sync.
