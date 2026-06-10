# Auto Microsite Generator

**Versión:** 1.0.0 | **Licencia:** LGPL-3 | **Autor:** MikeColangelo

Intercepta la creación de compañías (`res.company`) para generar automáticamente
un microsite completo: website, homepage, menús, theme views y campos personalizados.

## Descripción

Cuando se crea una nueva compañía en Odoo, este módulo genera de forma automática
todos los elementos necesarios para tener un microsite funcional: website asociado,
página de inicio, estructura de menús y configuración del tema corporativo.
También incluye un validador batch para detectar microsites incompletos.

## Dependencias

- `partner_microsite_manager` (canarias-platform)
- `website` (Odoo core)
- `theme_corporate_multi` (canarias-website)

## Uso

La generación es automática al crear una compañía. Para validación batch,
usar el modelo `microsite.validator` desde el backend.

## Créditos

### Autor
- [MikeColangelo](https://github.com/CanariasConectada)

### Licencia
[LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.html)
