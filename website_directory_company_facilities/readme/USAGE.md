1. Tick what a shop offers: **Settings › Companies › (the shop) › Facilities
   and services**, or the same fields wherever the merchant edits their own
   microsite.
2. Open `/comercio`. The sidebar gains a **Instalaciones y servicios** card,
   grouped by subdivision.
3. Click a chip to narrow, click it again to release it, or use **Quitar** to
   drop every tick at once. The zone, the category and the search box are kept
   throughout.

The filter reads `company.facility` records through `res.company.facility_ids`,
so a shop that has not ticked anything is simply never returned by it — it is
not hidden from the unfiltered directory.
