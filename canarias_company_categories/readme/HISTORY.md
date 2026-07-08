## 19.0.1.0.0 (2026-07-04)

First release. Seeds the Canarias Conectada business taxonomy (~130
categories under 8 roots such as Alimentación, Comercio, Servicios...) into
the OCA company categories (`res.company.category`, from OCA/multi-company
`res_company_category`) through a `post_init_hook`, replacing the retired
custom model `business.category` (`business_category_hierarchy`).

* Roots are seeded as *view* categories (grouping only); leaves as *normal*
  categories, one assignable per company (the Canarias Conectada business
  rule).
* The seed creates **no** `ir.model.data` entries: the records are fully
  owned by the user afterwards (rename/delete freely) and module updates
  never recreate or overwrite them.
* Existing categories with the same name/parent are skipped, so the hook is
  idempotent and safe to re-run.
