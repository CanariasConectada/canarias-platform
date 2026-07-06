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
