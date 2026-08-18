## 19.0.1.8.0 (2026-08-18)

Port of the legacy visual design of the Living Memory and Places of
Interest pages (design parity only, no comments/maps/submission form):

- Index: full-bleed photo hero (`hero_image` / `hero_subtitle` on the
  content type, seeded with the legacy artwork) with the search box inside
  it; sidebar filters rebuilt as stacked cards with auto-submit selects
  (category with counts, decades, emoji sort labels, 12/24/48 page size),
  total badge, active-search badge and a "Remove filters" button; results
  header bar with count and active-filter chips.
- Cards: legacy layout (220px photo, hover lift + zoom, bottom gradient
  overlay with year/likes/rating badges, category badge over the image)
  and a floating AJAX like button (vanilla JS `fetch` against the existing
  like route, CSRF included, `<noscript>` form fallback).
- Pager: legacy hand-built pagination (every page number, chevrons, query
  string preserved, anchored to `#entries_grid`) plus a page caption.
- Detail: legacy two-column layout — main card (image, title, badges,
  story, location, opening hours), gallery card, read-only reviews;
  sidebar with back button, information card and read-only rating card.
- New `?limit=` parameter whitelisted to 12/24/48; "best rated" sort; grid
  images served as `image_512` and the detail image as `image_1024`.
- New `sponsor_logo` / `sponsor_name` on the content type, rendered as a
  centered band at the bottom of every page of the type; seeded with the
  Gobierno de Canarias logo on Living Memory only (grant acknowledgement).

## 19.0.1.5.0 (2026-07-28)

Read-only display of the legacy ratings, restoring parity with the old
Living Memory pages (the migration brought the `rating.rating` rows to
production but nothing showed them):

- New `rating_avg` / `rating_count` computed fields on the item. The model
  deliberately does NOT inherit `rating.mixin`: in Odoo 19 that mixin
  extends `mail.thread` (chatter, followers, subtypes), which this
  read-only display does not need. The stats mirror the mixin's own
  normalization (consumed ratings with a real value) in one `_read_group`
  per batch.
- Detail page: average + star row + review list (author — "Visitor" when
  anonymous —, date, stars and feedback). Only shown for items that are
  approved and published; nothing renders when there are no ratings.
- Index cards: compact average (stars + value + count), computed for the
  whole page in a single query.
- No submission form: writing new reviews stays out of scope until the new
  review flow is decided.

## 19.0.1.3.0 (2026-07-10)

Security hardening of the public link and like flows:

- The `external_website` field now rejects any explicit scheme other than
  http/https (`javascript:`, `data:`, ...), removing a stored-XSS vector on
  the detail page. Scheme-less values (`www.example.com`) are allowed and
  normalized to https at render time, and the external link carries
  `rel="noopener nofollow"`.
- The like route validates the `redirect` parameter as a same-site absolute
  path before redirecting, closing the `/\evil.com` open-redirect bypass
  independently of Odoo's own `local=True` guard.

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
