Seeds the real Canarias Conectada business taxonomy (~130 categories, 8
roots such as Alimentación, Comercio, Servicios...) into the OCA **company
categories** (`res.company.category`, from OCA/multi-company
`res_company_category`).

Roots are seeded as *view* categories (grouping only); leaves as *normal*
categories, assignable to companies — **one category per company**, which is
the Canarias Conectada business rule.

This replaces the retired custom model `business.category`
(`business_category_hierarchy`). The seed creates **no** `ir.model.data`
entries: the user fully owns the records afterwards (rename/delete freely)
and module updates never recreate or overwrite them.
