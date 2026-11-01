# canarias-platform

Módulos core de la plataforma [Canarias Conectada](https://canariasconectada.es) para Odoo 19.

Gestión de zonas comerciales, microsites multi-tenant, directorio de empresas,
certificaciones (Silver Economy, Sostenibilidad), reseñas y puntos de interés.

## Módulos

| Módulo | Descripción |
|--------|-------------|
| `zones_company` | Zonas geográficas para organizar empresas |
| `business_category_hierarchy` | Categorías jerárquicas de comercio (3 niveles) |
| `website_directory` | Directorio público de empresas con filtros AJAX |
| `microsite_zones` | Core multi-tenant: zonas → empresas → microsites |
| `partner_microsite_manager` | Gestión de microsite desde ficha de contacto |
| `auto_microsite_generator` | Generación automática de microsites al crear empresa |
| `microsite_menu_manager` | Gestor centralizado de menús por tipo de site |
| `microsite_company_switch` | Sincronización de cookie de compañía en frontend |
| `partner_reviews` | Reseñas con valoraciones en microsites de comercio |
| `lugares_interes` | Galería de lugares de interés por microsite |
| `memoria_viva` | Galería de historia e imágenes históricas del comercio |
| `silver_economy` | Evaluación y certificación Silver Economy (Survey) |
| `sustainability` | Evaluación y certificación Sostenibilidad (Survey) |
| `zca_platform` | Plataforma de Zonas Comerciales Abiertas |
| `zones_toolbar_fix` | Toolbar de controles en páginas de zonas |
| `zzz_zone_fix` | Fixes del sistema de zonas (carga al final) |

## Permisos

Los grupos se asignan **a mano en la ficha de cada usuario**. La plataforma
dejó de usar `base_user_role` (y el `base_user_role_template` propio) el
2026-09-09: no hay roles ni recomposición automática de grupos. Un grupo
marcado en la ficha se queda; uno desmarcado, también. Cuando un módulo pide
un grupo (`website_pwa_chat`, `company_facilities`…), se marca en Ajustes ▸
Usuarios.

## Compatibilidad

- **Odoo:** 19.0 Community
- **Licencia:** LGPL-3 (AGPL-3 para `silver_economy`, `sustainability`)
- **Autor:** [MikeColangelo](https://github.com/CanariasConectada)
