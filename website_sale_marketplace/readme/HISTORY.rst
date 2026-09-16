19.0.1.8.1 (2026-09-16)
~~~~~~~~~~~~~~~~~~~~~~~

* The marketplace backfill skips the service products of delivery carriers:
  linking the portal to them moved the carrier away from its shop warehouse.

19.0.1.8.0 (2026-09-16)
~~~~~~~~~~~~~~~~~~~~~~~

* Logged-in customers of another company (the zone customers) can buy on a
  merchant shop again. ``website/models/ir_http.py`` runs their request with
  their own company, so creating the cart raised a company inconsistency on
  the customer (their partner is restricted to the zone) and the order's
  product check resolved the shop's products to the zone. Website orders in
  a shopper's own request now skip the check on the customer fields and
  evaluate the products with the order's company; at confirmation the
  order's company is linked to the customer's commercial partner, so the
  delivery order (and the merchant) can use it. Backend orders keep core's
  checks.

19.0.1.7.0 (2026-09-16)
~~~~~~~~~~~~~~~~~~~~~~~

* Every merchant shop gets its "Retirar en la tienda (<shop>)" in-store
  pickup method when its website is created or assigned
  (``res.company._ensure_shop_pickup_carrier``): the service product, the
  published ``in_store`` carrier on the shop's website and, when missing, a
  warehouse whose address is the company partner. Shops created after the
  migration had none and their checkout offered no delivery method at all.
  Marketplace (portal and zone) companies and companies without a website
  are skipped. Depends on ``website_sale_collect`` now.
