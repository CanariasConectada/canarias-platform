# Canarias Conectada — Documentación del sistema

Odoo 19 sobre Doodba. Cada pieza es un **addon** — el core nunca se toca.
Referencia de qué hace cada módulo, de qué depende y cuántos tests lo cubren.

> **Versión navegable (estilo API docs):**
> https://claude.ai/code/artifact/fd39ac57-838c-4756-939a-37e28f8210bf
>
> **Estado y salud del sistema (pre-cutover):**
> https://claude.ai/code/artifact/0244cba9-b2f6-445c-b7ea-c80db0a97e11

Resumen: **24 módulos propios + 13 del clúster de aislamiento · 1010 tests en verde · 0 módulos anómalos.**

---

## Frontend público

### Directorio y zonas
| Módulo | Para qué | Tests |
|---|---|---|
| `website_directory` | Directorio público de comercios (`/comercio`): filtro por categoría, búsqueda por nombre comercial, orden aleatorio por visitante. | 71 |
| `res_company_zone` | La zona comercial (barrio) de cada negocio; alimenta filtros de directorio y tiendas de barrio. | — |
| `canarias_company_categories` | Siembra la taxonomía de categorías de negocio. | — |
| `website_directory_company_certification` | Puente: sellos de certificación y su filtro en el directorio. | — |

### Tienda y marketplace
| Módulo | Para qué | Tests |
|---|---|---|
| `website_sale_marketplace` | Motor del marketplace: el portal muestra los productos de todos los comercios; cada microsite solo los suyos. Archivar un comercio los saca solo. | 18 |
| `website_sale_canarias` | El aspecto de la tienda: hero, sidebar de categorías, pill del comercio, filtrado AJAX. | 9 |
| `website_sale_comparison_canarias` | Comparador de productos moderno, disponible en todo producto. | 1 |
| `shop_frontend_tweaks` | Ajustes del shop (hero de microsites, barra, categorías buscables). | — |
| `product_return_warranty` | Garantía de devolución y plazo de entrega por producto. | — |

### Microsites y contenido
| Módulo | Para qué | Tests |
|---|---|---|
| `auto_microsite_generator` | Al crear una compañía, le provisiona website + menú + portada (idempotente). | — |
| `partner_microsite_manager` | Contenido del microsite editable desde la ficha de la compañía. | — |
| `website_local_content` | Galerías de contenido local (Memoria Viva + Lugares de Interés fusionados). | 53 |

### Comunidad y chat
| Módulo | Para qué | Tests |
|---|---|---|
| `discuss_channel_moderation` | Pre-moderación de comentarios de invitados antes de publicarse. | 101 |
| `discuss_channel_zone` | Canales de comunidad por zona; membresía derivada de cada usuario. | — |
| `website_pwa_chat` | La página `/chat` de comunidad, dentro del layout del PWA. | 20 |

> El soporte 1-a-1 usa el **Live Chat de Odoo** (`im_livechat`), integrado en Discuss, con los usuarios de soporte como operadores.

### PWA y notificaciones
| Módulo | Para qué | Tests |
|---|---|---|
| `website_pwa` | App instalable del sitio público (manifest, iconos, SW). Centralizada en el portal. | — |
| `website_pwa_push` | Web Push para la app del sitio. | — |
| `mail_push_guest` | Web Push para personas anónimas (`mail.guest`). | — |

### Certificaciones
| Módulo | Para qué | Tests |
|---|---|---|
| `company_certification` | Motor de sellos de certificación de compañía sobre Survey (umbrales, validez, reintentos). | 38 |
| `silver_economy` | Certificación «Silver Economy». | 11 |
| `sustainability` | Certificación «Sostenibilidad». | — |

### Reseñas · Login y marca
| Módulo | Para qué | Tests |
|---|---|---|
| `partner_reviews` | Reseñas de clientes sobre `rating.rating` con moderación por palabras prohibidas. | 25 |
| `website_login_branding` | Logos Canarias + ZCA en el login, más el botón «Continuar como invitado». | — |
| `website_login_company` | Fija como compañía activa la del website al hacer login. | — |

---

## Núcleo de datos — Aislamiento multi-compañía

Garantiza que un comercio nunca vea contactos ni productos de otro. Clúster OCA
portado 18→19, con módulos propios. Fork en `repos/multi-company`.

| Módulo | Origen | Para qué |
|---|---|---|
| `base_multi_company` | OCA | Base multi-compañía (`company_ids` m2m) para cualquier modelo. |
| `partner_multi_company` | OCA | Visibilidad individual de cada contacto por compañía. |
| `product_multi_company` | OCA | Visibilidad individual de cada producto por compañía. Base del marketplace. |
| `product_multi_company_stock` | OCA | No deja quitar compañía de un producto con stock/movimientos. |
| `partner_multi_company_restrict` | propio | Restringe visibilidad cruzada de contactos entre internos. |
| `product_company_default` | propio | Compañía actual por defecto en productos nuevos. |
| `multi_company_field_visible` (+2 puentes) | propio | Deja al no-multicompañía gestionar su propia compañía. |
| `res_company_category` | OCA | Categorías de compañía (base de la taxonomía del directorio). |
| `res_company_category_partner` | propio | Categoría de compañía desde la ficha del contacto principal. |
| `mail_thread_followers_access_fix` | propio | Evita crash cuando un seguidor no es legible (chatter multi-compañía). |
| `res_company_search_view` | OCA | Vista de búsqueda de compañía. **Idéntico a upstream → candidato a soltar el fork.** |

---

## Validación — por qué existe cada suite

1010 tests en verde. No cubren «que Odoo funcione», sino las reglas propias que,
si se rompen, rompen el negocio.

| Suite | Nº | Por qué |
|---|---|---|
| migraciones | 362 | Cada entidad probada contra un ORM simulado: qué escribe, qué se niega a escribir, idempotencia. Nació del bug que dobló 7 compañías. |
| fixes | 59 | Los arreglos idempotentes sobre la base viva: orden de ejecución y que `dry_run` no escriba. |
| discuss_channel_moderation | 101 | Ningún mensaje sin aprobar llega por ninguna ruta; un invitado no lee el retenido de otro. |
| website_directory | 71 | Búsqueda por zona/categoría/nombre comercial, paginación sin solapes, imagen pública sin fugas. |
| website_local_content | 53 | Aislamiento del contenido, «me gusta» sin duplicar, permisos de envío. |
| company_certification | 38 | Umbrales de sello, validez, reintentos; no forjar evaluación completada. |
| partner_reviews | 25 | Moderación por palabras prohibidas; un empleado no altera reseñas ajenas. |
| website_pwa_chat | 20 | El chat dentro del layout del PWA y con moderación de invitados. |
| website_sale_marketplace | 18 | Agregación cross-comercio con aislamiento; producto nuevo no se cuela en zona ajena; archivar barre. |
| website_sale_canarias | 9 | El shop no filtra catálogo ajeno en un microsite; excluye archivados. |
| resto (silver, comparador, …) | +254 | Certificaciones verticales, comparador siempre-visible y demás módulos propios. |

---

## Módulos retirados (no instalar)

Presentes en el repo pero **no instalados**: legacy que la reforma reemplazó.

| Retirado | Reemplazado por |
|---|---|
| `memoria_viva`, `lugares_interes` | `website_local_content` |
| `zzz_zone_fix` | `website_sale_canarias` |
| `microsite_zones`, `zones_company`, `zones_toolbar_fix` | `res_company_zone` + marketplace |
| `microsite_menu_manager`, `microsite_company_switch` | `auto_microsite_generator` + `website_login_company` |
| `zca_platform`, `theme_corporate_multi` | los módulos propios de arriba |
