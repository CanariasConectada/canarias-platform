On a product, open **Sales › General Information** and fill in the two groups
added below the internal notes:

* **Return warranty** — Hidden, No return warranty, 14 / 30 / 60 / 90 days, or
  Custom (a number plus days, weeks, months or years).
* **Delivery time** — Hidden, No home delivery, 24 hours, 2-3 / 3-5 / 5-7 days,
  or Custom (a number plus hours, days or weeks).

Whatever is not Hidden shows up under the price on the public product page, one
line each, with an icon.

The block is rendered by Odoo's *Terms and Conditions* optional template, which
the product page calls under `is_view_active()`. Switching that option off in
the website editor therefore hides this information too — that is deliberate,
so the shop keeps a single switch for the whole legal footer of the product.
