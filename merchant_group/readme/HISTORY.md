## 19.0.2.1.0 (2026-09-15)

* Gift cards and eWallets open to merchants: both menus (Sales > Products
  and eCommerce > Loyalty) and create/delete on loyalty cards.

## 19.0.2.0.0 (2026-09-15)

- **The default merchant profile.** Comercios now also implies purchase
  user, inventory user, invoicing (`account.group_account_invoice`) and
  product variants, and grants read/write/create/delete on the loyalty
  program, rule, reward and communication models (company record rules
  still apply). The CRM root menu is gated here to salesman + manager, as
  core intends (the production database only had the manager), and the
  discount & loyalty entries of Sales ▸ Products and Website ▸ eCommerce
  open to Comercios. Gift cards and eWallets stay administrator-only.
- **Merchant dashboard**, an opt-in checkbox per user, gives a "My
  Dashboard" root app (module `board`). The spreadsheet dashboards root
  moves here from `partner_microsite_manager` and stays administrator-only.

## 19.0.1.0.0 (2026-09-14)

- First release: the **Comercios** group, and every new internal user gets it.
