## 19.0.1.0.1 (2026-10-01)

- The map query cleans the address fields: HTML entities are decoded,
  non-breaking spaces become spaces, whitespace is collapsed, and a zip the
  street repeats is dropped. 29 shop partners carried a literal
  `&nbsp;35010` in `street` from the 2026 import, which reached Google as
  `%26nbsp%3B35010` and showed a city-wide map. A clean address gives the
  same URL as before.

## 19.0.1.0.0

- First version: `res.partner._canarias_map_embed_url()` and the
  `website_map_embed.map_iframe` template.
