## 19.0.2.0.0

Ported from the legacy `canarias-website` repository, where the module was
installed in production but had never been carried over to the Doodba
deployment. Two behaviour changes and one rename:

* The template now **replaces** Odoo's hardcoded returns and shipping text
  instead of appending to it. In the legacy version both texts rendered
  together, so a product announcing "Delivery in 24 hours" also announced
  "Shipping: 2-3 Business Days" right above it.
* Selection keys and labels moved to English, per the project convention of
  English code with `i18n/es.po` translations.
* `return_warranty_custom_days` became `return_warranty_custom_value`, since it
  holds weeks, months or years just as often as days — and to match
  `delivery_days_custom_value`.

**Migration mapping** for the data still living in the legacy database
(1 product of 1571 at the time of the port):

| Legacy value | Ported value |
| --- | --- |
| `oculto` | `hidden` |
| `sin_garantia` / `sin_entrega` | `none` |
| `14_dias` / `30_dias` / `60_dias` / `90_dias` | `14_days` / `30_days` / `60_days` / `90_days` |
| `2_3_dias` / `3_5_dias` / `5_7_dias` | `2_3_days` / `3_5_days` / `5_7_days` |
| `24h` | `24h` |
| `personalizado` | `custom` |
| `dias` / `semanas` / `meses` / `anos` | `days` / `weeks` / `months` / `years` |
| `horas` | `hours` |
