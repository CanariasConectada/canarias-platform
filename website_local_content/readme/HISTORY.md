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
