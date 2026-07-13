This module lets a single "marketplace" website list the published products of
**every** company, while every other website keeps the strict per-company
isolation provided by ``product_multi_company``.

Under ``product_multi_company`` a website's shop only lists products whose
``company_ids`` include the website's own company. That is exactly what each
merchant microsite needs, but it also means a central portal owned by one
company can never show the whole catalogue.

This module adds a per-website ``Marketplace`` flag. When a website is flagged
as a marketplace, its company is added as an extra allowed company on every
product (existing ones at install / when the flag is set, new ones on create).
Because a product scoped to ``[merchant, marketplace]`` is visible to the
merchant and to the marketplace but **not** to any other merchant, the central
shop, its product pages and cart all work at every layer with no controller or
routing overrides, and merchant websites stay fully isolated. Products keep
belonging to their own merchant company; the marketplace company is only an
extra visibility scope.
