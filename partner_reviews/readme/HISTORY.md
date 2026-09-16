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
