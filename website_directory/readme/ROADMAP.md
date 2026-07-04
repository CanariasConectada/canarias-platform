* **Zones**: the legacy zone cluster (`zones_company` and friends) is
  retired and its replacement is not designed yet. Meanwhile the entry
  keeps the `zone` selection as plain data and the zone is inferred from
  the website domain. The future zone module must override
  `res.company._get_directory_zone()` (new entries),
  extend `_get_directory_sync_fields()` and, if needed, the
  `directory_sidebar_extra` template.
* **Microsites**: the base module only reads base + website fields to build
  the entry URL. Microsite modules (custom domains, subdomains) must
  override `res.company._get_directory_extra_website_url()` and extend
  `_get_directory_sync_fields()` with their trigger fields.
* **Silver Economy / Sustainability filters**: removed from the base module
  (they queried survey models without declaring the dependency). When those
  verticals are reformed, create the bridge modules
  `website_directory_silver_economy` and `website_directory_sustainability`
  using the extension points: controller hooks `_get_extra_filter_domain()`
  / `_get_extra_pager_args()` and the sidebar template hook
  `directory_sidebar_extra` (`<div id="o_wd_sidebar_extra"/>`).
* **Website menus**: the old `data/website_directory_data.xml` (commented
  out for months) was removed. Website menu entries pointing to
  `/directorio` will be created by the new zone/website module.
* **Data migration to 19.0.5.0.0** (handled by the external migration
  script, documented here only):
  * old entry `category_ids` (M2M to the retired `business.category`) must
    be mapped to the company `category_id` (M2O to `res.company.category`,
    matching by name/hierarchy) — the entry field is now a stored related,
  * legacy `zone` spellings (`lomo_los_frailes`, `lomo los frailes`) can be
    normalized to `lomolosfrailes` (templates tolerate them meanwhile),
  * old manual image fields were replaced by `image.mixin`: copy the old
    `image` column into `image_1920` and drop the old resized columns.
