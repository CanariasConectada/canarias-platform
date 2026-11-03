## 19.0.3.9.0 (2026-09-22)

* Platform-wide switch for the comparator (client decision): *Website >
  Configuration > Settings > "Price comparator"*, stored in the system
  parameter `website_sale_comparison_canarias.enabled` and read in one place,
  `website._wscc_comparison_enabled()`. Shipped **off** (noupdate data, so an
  update never flips what the admin set) and re-activatable without a
  deploy. Off means not rendered: the Compare buttons on the cards (classic
  listing and AJAX grid), the Compare prices button and its picker on the
  product page, core's own compare buttons (products with variants), and
  core's bottom bar (its interaction is matched on a `data-wscc-comparison`
  marker the layout puts on `<body>` only while the switch is on, so it is
  never instantiated). `/shop/compare/candidates` answers the empty
  shape the picker already draws, and `/shop/compare` redirects to `/shop`.
  Module and data stay installed either way.
