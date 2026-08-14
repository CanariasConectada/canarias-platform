Per-product return warranty and delivery time on the shop page.

Odoo hardcodes two claims in `website_sale.product_terms_and_conditions` —
*"30-day money-back guarantee"* and *"Shipping: 2-3 Business Days"* — and shows
them on every product of every website, in English, whether or not the shop can
keep them. On a platform of independent local shops that text is not a default:
it is a promise nobody agreed to.

This module removes those two lines and lets each shop state its own policy on
each product instead. The Terms and Conditions link stays, since that one is a
legal reference rather than a claim.

Both policies default to **Hidden**, so installing the module changes no product
page until somebody fills the fields in.
