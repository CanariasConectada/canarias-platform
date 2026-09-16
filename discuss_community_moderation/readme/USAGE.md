Install the module; nothing else is mandatory.

- Every existing moderation row — the four rows `discuss_channel_zone`
  seeds included — comes out of the install with **Moderate Community
  Guests** and **Moderate New Community Members** on and **Trust
  Threshold** at 3. No data migration is involved: the ORM applies the
  field defaults to pre-existing rows when it adds the columns, and the
  seed data's `noupdate="1"` is never touched.
- Tune per channel from *Settings → Technical → Discuss Moderation*: the
  three new fields sit next to the engine's guest/portal switches.
  A threshold of 0 keeps members unmoderated while still holding guests.
- Moderation itself is unchanged: held community messages land in the same
  queue, the same moderators approve or reject them, and the author's
  Discuss thread updates live in both directions.
