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
