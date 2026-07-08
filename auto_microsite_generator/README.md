# Auto Microsite Generator

**Versión:** 19.0.1.0.0 | **Licencia:** AGPL-3 | **Autor:** Canarias Conectada

Aprovisiona automáticamente un website, una portada y el menú estándar cuando
se crea una compañía (`res.company`). En la plataforma Canarias Conectada cada
comercio es una compañía con su propio website (multi-website nativo); al
crear la compañía este módulo crea el website, publica una portada por defecto
en `/` y garantiza las entradas de menú estándar (Inicio, Tienda, Comercios).

La generación es **no destructiva y consciente de la migración**: el contenido
web traído "tal cual" por la migración de datos (páginas COW, vistas y menús
anclados a IDs externos `canarias_mig.*`) se detecta y **nunca se sobreescribe**;
el generador solo crea lo que falta. La portada rica y editable es
responsabilidad de la acción *Publish Homepage* de `partner_microsite_manager`,
que solo sobreescribe a petición explícita, nunca en este flujo automático.

La documentación detallada está en los fragmentos de [`readme/`](readme/):
[descripción](readme/DESCRIPTION.md) · [uso](readme/USAGE.md) ·
[hoja de ruta](readme/ROADMAP.md) · [historial](readme/HISTORY.md) ·
[contribuidores](readme/CONTRIBUTORS.md).

## Dependencias

- `website` (Odoo core)

## Créditos

### Autor
- [Canarias Conectada](https://github.com/CanariasConectada)

### Licencia
[AGPL-3](https://www.gnu.org/licenses/agpl-3.0.html)
