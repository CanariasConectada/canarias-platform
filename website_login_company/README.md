# Website Login Company

**Versión:** 19.0.1.0.0 | **Licencia:** AGPL-3 | **Autor:** Canarias Conectada

Al iniciar sesión desde un website cuya compañía difiere de la del usuario,
establece la cookie de compañía activa (`cids`) con la compañía del website,
de modo que cada comercio aterriza en el contexto de su propia compañía en
su microsite. Las demás compañías permitidas siguen disponibles en el
selector, solo que no seleccionadas.

Sustituye el parche manual del core de producción en
`addons/web/controllers/home.py` (`Home._login_redirect`) por un addon
instalable:

- Solo fuerza la cookie si el usuario tiene acceso a la compañía del
  website; en caso contrario se mantiene el comportamiento estándar.
- Es un no-op estricto sin website en la petición (XML-RPC, hosts sin
  website, bases de datos sin website): corrige el histórico HTTP 500 en
  el login en contextos sin website.
- Cualquier error inesperado se registra y se absorbe: el login nunca se
  rompe por la cookie de compañía.

La documentación detallada está en los fragmentos de [`readme/`](readme/):
[descripción](readme/DESCRIPTION.md) · [uso](readme/USAGE.md) ·
[historial](readme/HISTORY.md) · [contribuidores](readme/CONTRIBUTORS.md).

## Dependencias

- `website` (Odoo core)
