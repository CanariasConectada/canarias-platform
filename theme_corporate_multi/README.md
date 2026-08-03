# Tema Maestro Corporativo Multi-Website

Cabecera, pie y portada corporativos compartidos por los microsites de la
plataforma. Aporta la identidad visual que en el sistema antiguo llevaban 203 de
los 275 sitios.

## Qué aplica al instalarse

Las plantillas heredan de `website.layout`, así que el pie corporativo, el
logotipo del comercio en la cabecera, la barra de cookies y la retirada del
copyright de Odoo se aplican a **todos** los websites en cuanto el módulo está
instalado. No hace falta asignar nada sitio a sitio.

La portada (`corporate_homepage`) y la página de servicios
(`corporate_services`) son plantillas disponibles; qué sitio las usa es una
decisión de datos, no del módulo.

## Qué cambia respecto al módulo original

Este módulo es un port reformado de `theme_corporate_multi` 19.0.1.1.0 del repo
`canarias-website`. No es una copia.

| Original | Aquí | Por qué |
|---|---|---|
| `depends: zones_company` | `depends: res_company_zone` | `zones_company` está jubilado. La zona pasó de ser un many2one a un campo Selection en la compañía. |
| `res_company.zone_id.name` en las vistas | `res_company.commercial_zone` | Consecuencia del cambio anterior. |
| `models/res_company.py` con 5 campos `social_*` | eliminado | Odoo 19 ya define `social_facebook`, `social_instagram`, `social_twitter`, `social_youtube` y `social_linkedin` en `res.company`. Redefinirlos los sobrescribía en silencio. |
| `hooks.py` | eliminado | 67 líneas de instrumentación de depuración que parcheaban `IrUiView._combine` y escribían un JSON en `/home/odoo/.cursor/debug.log` en cada combinación de plantilla. No estaba declarado en el manifest, así que nunca llegó a ejecutarse. |
| `views/shop_templates.xml` | eliminado | El fichero solo contenía comentarios. |
| Páginas legales propias | eliminadas | Ver abajo. |
| `<link>` y `<script>` crudos en `<head>` | bundle `web.assets_frontend` | Ver abajo. |
| `© 2025` fijo | `website.get_footer_year()` | Un pie con el año equivocado en 200+ sitios públicos parece abandonado. |
| Sellos desde `ir.config_parameter` | desde `res.company` | Ver abajo. |
| — | enlace a `/aviso-legal` en el pie | Es obligatorio (LSSI art. 10) y solo se llegaba desde el menú. |

### Las páginas legales tienen un solo dueño

El módulo original publicaba `/politica-privacidad`, `/politica-cookies` y
`/terminos-condiciones` con registros `website.page` **sin `website_id`**. Esas
tres URLs ya las publica `partner_microsite_manager`.

Instalarlo tal cual habría dejado dos páginas compitiendo por cada URL, con
Odoo eligiendo una de las dos, y el texto legal real —el que nombra al comercio
y su NIF— podría quedar tapado por uno genérico.

Aquí el dueño de lo legal es `partner_microsite_manager`, y por eso figura como
dependencia dura. Hay un test que falla si este módulo vuelve a publicar
cualquier `website.page`.

### Los sellos leen la certificación, no una copia de ella

`get_certifications()` leía dos claves de `ir.config_parameter` llamadas
`website.<id>.has_silver` y `website.<id>.has_sostenible`, escritas a mano. Eso
es una copia de la verdad, y se desincronizaba: si una certificación caducaba,
se revocaba o se concedía desde el backend, el sello seguía diciendo lo que
dijera el parámetro, para siempre.

Ahora lee `res.company.silver_certification_level` y
`res.company.sustain_certification_level`, que son los campos que calculan
`silver_economy` y `sustainability`. El sello ya no puede contradecir a la
certificación.

Los campos solo existen si su módulo vertical está instalado, así que la lectura
es defensiva: sin el módulo no hay sello, nunca un error. El pie se renderiza en
todas las páginas de todos los microsites; no puede permitirse una excepción.

### Los estáticos van por el pipeline de assets

El módulo original inyectaba cada CSS y cada JS como etiquetas `<link>` y
`<script>` dentro de un `<head>` construido por QWeb, más un bloque `<style>` en
línea. Eso funciona, pero se salta el pipeline: sin empaquetado, sin
invalidación de caché, sin minificar, y una petición bloqueante extra por
fichero en cada página de cada microsite.

Además, **dos de esos ficheros no se cargaban en absoluto** porque nadie los
referenciaba. Portarlos tal cual habría portado también esa avería.

`footer_certificaciones.js` no se ha traído: manipulaba los sellos desde el
navegador, y ahora los pinta el servidor con el dato correcto.

## Instalación

Instalar un tema **reescribe vistas COW por website**. No va directo: hay que
probarlo antes en una copia desechable y comparar el render.
