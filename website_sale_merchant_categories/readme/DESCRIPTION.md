Merchants curate the category tiles shown at the top of their own shop
without touching what the other shops see.

Two mechanisms, both scoped to the merchant's site:

- **A per-site image for a shared category.** `website.category.tile` sits
  between a website and a `product.public.category`. The tile renderer of
  `website_sale_canarias` prefers this image on that website and falls back
  to the shared `cover_image` everywhere else.
- **Own categories.** A merchant may create `product.public.category`
  records pinned to their own website (`website_id` is forced on the
  server), and rename or delete only those, from their rows in the same
  "Shop categories" list. The shared categories stay read-only for them.
