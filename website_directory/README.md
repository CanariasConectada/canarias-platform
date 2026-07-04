# Website Directory

**Versión:** 19.0.5.0.0 | **Licencia:** AGPL-3 | **Autor:** Canarias Conectada

Directorio público de comercios del marketplace de Canarias Conectada,
servido en `/directorio`: cards con logo, filtro de categorías en cascada
(jerarquía OCA `res.company.category`, descendientes incluidos), búsqueda
asíncrona, paginación configurable y rotación diaria equitativa de los
comercios. La entrada de cada comercio (`website.directory.entry`) se
sincroniza automáticamente desde su compañía.

La documentación detallada está en los fragmentos de [`readme/`](readme/):
[descripción](readme/DESCRIPTION.md) · [uso](readme/USAGE.md) ·
[hoja de ruta](readme/ROADMAP.md) · [historial](readme/HISTORY.md) ·
[contribuidores](readme/CONTRIBUTORS.md).

## Dependencias

- `website` (Odoo core)
- `res_company_category` (OCA/multi-company, port 19.0)

## Puntos de extensión

- `res.company._get_directory_zone()` / `_get_directory_extra_website_url()`
  / `_get_directory_sync_fields()` — para los futuros módulos de zonas y
  microsites.
- Controlador: `_get_extra_filter_domain(kw)` y `_get_extra_pager_args(kw)`
  — para los puentes `website_directory_silver_economy` y
  `website_directory_sustainability`.
- Plantilla `directory_sidebar_extra` — hueco del sidebar para tarjetas de
  filtros adicionales.

## Créditos

### Autor

- Canarias Conectada

### Mantenedores

- [mikecolangelo](https://github.com/CanariasConectada)

### Licencia

[AGPL-3](https://www.gnu.org/licenses/agpl-3.0.html)
