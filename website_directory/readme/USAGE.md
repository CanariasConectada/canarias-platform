1. Assign a category to each company (Settings > Companies), using the
   hierarchy of `res.company.category` (the Canarias taxonomy can be seeded
   with the `canarias_company_categories` module).
2. Keep the company checkbox **Show in Directory** enabled (default). The
   directory entry is created and updated automatically; the header button
   **Synchronize with Directory** forces a manual refresh.
3. Open `/comercio` on the website. Routes:
   * `/comercio` — full directory (zone inferred from the website domain),
   * `/comercio/zona/<zone>` — explicit zone filter,
   * `/comercio/categoria/<id>` — category filter (descendants included),
   * `/comercio/img/<id>` — public image (entry image or company logo).

Curated fields are never overwritten by the synchronization: the entry
`zone`, `short_description`, `description` and published state only change
when edited by hand (the zone is set once, on entry creation).
