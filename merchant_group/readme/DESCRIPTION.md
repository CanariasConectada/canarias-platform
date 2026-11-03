Until the user roles were retired, "make this person a merchant" was one
gesture. This module brings the gesture back as a plain group, **Comercios**,
and makes it the default merchant backend profile of the platform.

Ticking **Comercios** gives a merchant their shop and catalogue (with
variants), their website and eCommerce, their seals, their mailings, their
reviews, and — since 19.0.2.0.0 — CRM, Purchases, Inventory, Invoicing of
their own company and the discount and loyalty programs of their own
company. Gift cards and eWallets are deliberately left out.

It is a group, not a role: nothing is recomposed behind anyone's back. A
permission granted by hand on top of it stays; unticking it takes away only
what it gave.

The group is also handed to **every new internal user**, through Odoo's own
`base.default_user_group` hook.

A second, opt-in checkbox, **Merchant dashboard**, gives one user a personal
"My Dashboard" (module `board`) as a root app, without opening the
platform's spreadsheet dashboards, which stay with the administrators.

The module also owns the menu gates the profile depends on (CRM root,
loyalty entries, spreadsheet dashboards root) in replace form, so that an
update of the module that ships a menu cannot flip a gate back.
