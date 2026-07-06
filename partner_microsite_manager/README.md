# Partner Microsite Manager

**Versión:** 19.0.1.0.0 | **Licencia:** AGPL-3 | **Autor:** Canarias Conectada

Contenido del microsite del comercio gestionado desde el formulario de la
compañía. Cada comercio es una `res.company` con su propio website
(multi-website nativo): la pestaña **Microsite** de la compañía edita el
nombre comercial, imagen de cabecera, horario, entrega, parking, secciones
"sobre nosotros" / "servicios", banners y mapa. La portada pública es una
plantilla QWeb **dinámica** que lee esos campos al renderizar: guardar el
formulario actualiza la web al instante, sin regenerar HTML ni reescribir
vistas. La acción **Publish Homepage** instala la plantilla como portada
del website de la compañía una única vez.

La documentación detallada está en los fragmentos de [`readme/`](readme/):
[descripción](readme/DESCRIPTION.md) · [uso](readme/USAGE.md) ·
[hoja de ruta](readme/ROADMAP.md) · [historial](readme/HISTORY.md) ·
[contribuidores](readme/CONTRIBUTORS.md).

## Dependencias

- `website` (Odoo core)

## Créditos

### Autor

- Canarias Conectada

### Mantenedores

- [mikecolangelo](https://github.com/CanariasConectada)

### Licencia

[AGPL-3](https://www.gnu.org/licenses/agpl-3.0.html)
