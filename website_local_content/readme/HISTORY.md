## 19.0.1.1.0 (2026-07-09)

Per-website scoping of the public pages, restoring the parity with the
legacy per-zone modules (each vertical lived on a single microsite):

- New `website_ids` Many2many on the item: empty means visible on every
  website (existing/migrated items keep their behaviour), otherwise the
  item only appears on the selected websites. Index, detail, image and
  like routes all honour it (404 elsewhere), and the sidebar category
  counts and decade filter only count visible items.
- The content type `website_ids` keeps gating the whole vertical: on a
  website where the type is not available every route answers 404, as
  the legacy modules did.
- The public pages now set a real `<title>` (content type name — and item
  name on the detail page — plus the website name) instead of the generic
  template name.

## 19.0.1.0.0

First reformed release, fusing the legacy `memoria_viva` and
`lugares_interes` clone modules into one parameterizable module:

- Content verticals become `website.local.content.type` data records.
- Dead social features removed: comments, star ratings, banned words,
  promotional ads/banners, per-item events (all ~0 rows in production).
- Public JSON submission API (which auto-created portal users) removed.
- Custom WebP image pipeline replaced by the standard `image.mixin` +
  `ir.binary` streaming.
- Hardcoded website/category ids removed; per-website availability is a
  Many2many on the content type.
