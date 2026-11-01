A price comparator for the Canarias Conectada shops, built on Odoo's own
`website_sale_comparison`.

* A **Compare** button on every product card (classic listing and the
  aggregated shop's AJAX grid), not only on products with variants, feeding
  core's comparison list and bottom bar.
* A **Compare prices** button on the product page that opens a picker asking
  *against what*: the whole platform, the product's commercial zone, outside
  that zone, or the shop that sells it; narrowed by category and by name.
  Every scope resolves to a website and its own `sale_product_domain()`, so
  the picker can never show a product the visitor could not browse to.
* A platform-wide **switch** (Website > Configuration > Settings > "Price
  comparator"), off by default, that removes every compare control from
  every shop without uninstalling anything.
