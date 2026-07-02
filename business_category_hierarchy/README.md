# Business Category Hierarchy

**Versión:** 19.0.2.0.0 | **Licencia:** AGPL-3 | **Autor:** Canarias Conectada

Categorías de comercio jerárquicas (`business.category`) para segmentar las
empresas del marketplace de Canarias Conectada. Se asignan a `res.company`
(`business_category_ids`) y las usa como filtro el directorio público
(`website_directory`).

La documentación detallada está en los fragmentos de [`readme/`](readme/):
[descripción](readme/DESCRIPTION.md) · [uso](readme/USAGE.md) ·
[historial de cambios](readme/HISTORY.md) ·
[contribuidores](readme/CONTRIBUTORS.md).

## Dependencias

- `contacts` (Odoo core)

## Configuración

*Contactos > Configuración > Categorías de Comercio* para gestionar el árbol;
*Importar Categorías* para la carga masiva desde texto.

En la instalación se siembra la taxonomía por defecto (~130 categorías) sin
identificadores externos: el usuario es dueño de los registros y las
actualizaciones del módulo nunca los recrean ni sobreescriben.
