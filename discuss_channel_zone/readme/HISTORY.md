## 19.0.1.1.1 (2026-09-25)

- Channel names and descriptions are no longer translatable fields (an
  unreleased build made them so and turned the columns into `jsonb`). The
  end-migration converts the columns back to plain text, keeping the `en_US`
  value, on the databases that got the unreleased build; a no-op elsewhere.
  Only `en_US` survives that conversion: any other language written while
  the columns were `jsonb` is dropped (lab only; production never had it).

## 19.0.1.1.0 (2026-09-25)

- The four seeded channels (Canarias Conectada and the three neighbourhoods)
  are shown in the reader's language: their name and description are
  translated at display time (`display_name` and the Discuss store payload),
  as long as nobody renamed them. The stored columns stay plain text, so
  renames, search and mentions are unchanged and no schema change is needed.
- Migration: the XML indentation is stripped from the four seeded
  descriptions (only when unedited).
- Translations of the seeded channels and of every UI string of the module in
  Spanish, French, German, Italian, Portuguese and Polish.

## 19.0.1.0.0 (2026-08-04)

- First release: four seeded channels, the `Community Chat: Registered Member`
  group that closes the neighbourhood channels to visitors, `res.users.chat_zone`,
  the idempotent membership sync with its create/write/company triggers, the
  nightly reconciliation cron and the initial `post_init_hook` sync.
