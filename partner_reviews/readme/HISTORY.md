# 19.0.3.0.0 (2026-09-22)

- The forbidden words list moved to the shared platform module
  `website_moderation_forbidden_word` (one list for merchant reviews and
  local content comments, client decision). `review.forbidden.word` is
  gone: the migration copies every row into `moderation.forbidden.word`
  (entries the shared seed already holds are skipped but take the old
  row's active state, so a word that held reviews before keeps holding
  them even where the seed ships it archived), deletes its orphan xmlids
  and drops the old table.
- Matching now ignores accents on both sides (`IMBECIL` hits `imbécil`)
  and keeps the whole-word rule; multi-word entries keep working.
- *Reviews > Forbidden Words* stays for review administrators and opens the
  shared list; system administrators also find it under *Settings >
  Moderation*. Review administrators create, edit and archive entries but
  cannot delete them (the list is platform-wide). Review users no longer
  read the list (it was never shown to them).
- The migration is covered by a test that replays it against a throwaway
  copy of the old table (`tests/test_migration_forbidden_words.py`).

# 19.0.2.2.1 (2026-09-16)

- The *Reviews* page comes after *Facilities and services* in both the
  content editor and the company form's Microsite notebook, whatever the
  install order (the two views get priority 99).

# 19.0.2.2.0 (2026-09-16)

- Merchants switch their own reviews page on and off from the content
  editor (*Website > Page content*), in a new *Reviews* tab that also shows
  the average rating, the number of published reviews and a link to the
  page (client request). The value goes through the editor's whitelist and
  ownership check; the company write keeps adding or removing the *Reviews*
  entry of the shop's website menu. Depends on `partner_microsite_manager`.
- On the company form the switch moved from next to the website field to a
  *Reviews* page of the Microsite notebook, mirroring the editor.

# 19.0.2.0.0 (2026-07-06)

Full OCA-style reform of the legacy module. Breaking changes:

- The ad-hoc models `partner.review.rating` and `partner.review.comment`
  are replaced by native `rating.rating` records attached to `res.company`
  (production data is migrated by the platform migration script).
- A review is now one record: stars + optional comment together, instead
  of separate rating and comment objects.
- Public threaded replies were dropped; the merchant answers through the
  native `publisher_comment` field from the backend instead.
- The `enable_reviews` flag moved from `res.partner` to `res.company`,
  matching the one-company-per-merchant architecture; the coupling with
  `partner_microsite_manager` was removed.
- `partner.review.settings` singleton replaced by a standard system
  parameter (`partner_reviews.allow_comments`) exposed in Website settings.
- `partner.review.palabra.prohibida` renamed to `review.forbidden.word`;
  the default list was curated (over-flagging generic words like "tonto"
  or "basura" were removed).
- The frontend is now rendered fully server-side with CSRF-protected
  forms; the legacy JavaScript (and its CSRF-disabled JSON endpoints) was
  removed.

# 19.0.1.0.0

Legacy implementation with custom review models.
