## 19.0.2.2.0 (2026-09-22)

Rating comments go through the shared forbidden-word list
(`website_moderation_forbidden_word`, client decision 2026-09-22):

- A comment that hits the list publishes its STARS at once (they count in
  the item's average and total) while its text waits for a local content
  manager: new `feedback_moderation_status` (`approved` / `pending` /
  `rejected`) on `rating.rating`, scoped to local content ratings.
- The public detail page hides a held text from everyone but its author,
  who sees it with a neutral "Your comment will be published after
  review." notice (never the matched word). A rejected text is hidden
  from everyone, the author gets "Your comment was not published."; the
  text is kept in the database for the audit trail.
- Editing a comment re-evaluates only when the text changed: re-posting
  the same comment with other stars keeps the manager's decision and
  spawns no new notification.
- Managers get an email (`mail_template_comment_moderation`) and a to-do
  activity on the author's contact, one open activity per manager and
  author; without any manager the system administrators are notified.
  `skip_review_notifications` in the context silences both, like
  `partner_reviews`.
- New *Local Content > Comments pending review* menu (list with approve
  and reject buttons, default filter on pending), mirrored under
  *Settings > Moderation > Local Content Comments* for administrators.
  Only local content managers and system administrators may change the
  status by hand.
- Held and rejected comments are readable by their author, the local
  content managers and system administrators only (global record rule
  `rule_rating_local_content_held_comment`; published comments and the
  ratings of other models stay as readable as before; the public page
  reads through sudo).
- Approving, rejecting or deleting a held rating closes the managers'
  to-dos once nothing of that author is held any more.
- The three older test classes that ran at install time now run
  `post_install`: on a database where `purchase_stock` is installed
  (production), its NOT NULL `group_rfq` column on `res_partner` breaks
  partner creation for any module loaded before it, so at-install tests
  creating users failed regardless of this module's own code.

## 19.0.2.1.0 (2026-09-16)

Interactive likes and ratings on the public detail page (the legacy
pages let visitors like and rate from inside the place, not only from
the card):

- Like button in the information card of the detail page, on the same
  like route and AJAX code as the card (`<noscript>` form fallback,
  liked state rendered as a filled, disabled heart). The JS now finds
  like counters by `data-like-counter-for="<item id>"`, so the card and
  the detail page share it.
- Rating form in the rating card for logged-in users: pure CSS radio
  star picker (1-5) and an optional comment capped at 1000 characters,
  posted to `/explora/<type>/rate/<id>`; one consumed `rating.rating`
  per partner per item (create or update), removable through
  `/explora/<type>/rate/<id>/delete`. Both routes only ever touch the
  caller's own rating and refuse unpublished or hidden items. Anonymous
  visitors get a "log in to rate" link back to the rating card; an
  out-of-range star value comes back with a "choose 1 to 5 stars" alert.
- Partial unique index `website_local_content_rating_partner_uniq` on
  `rating_rating (res_id, partner_id)` for this model only (created in
  `init()` after collapsing existing duplicates to the most recent row);
  a concurrent duplicate insert falls back to updating the existing row.

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
