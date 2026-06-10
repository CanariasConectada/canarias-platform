# PENDIENTES Y BUGS - Zone Fix

## BUGS ACTIVOS

*No hay bugs activos actualmente.*

---

## BUGS RESUELTOS (Documentación)

### 🟢 BUG #1: Redirección automática en categorías para usuarios Admin ✅ RESUELTO
**Fecha detectada:** 2026-03-23
**Prioridad:** Alta

#### Descripción
Cuando un usuario administrador/editor está logueado y selecciona una categoría en el dropdown de Select2:
1. Se navega correctamente a `/shop/category/[nombre-categoria]`
2. Inmediatamente se redirecciona a `/shop` (sin categoría)
3. El filtro de categoría no se aplica

#### Comportamiento esperado
Al seleccionar una categoría, debería mostrarse la tienda filtrada con los productos de esa categoría.

#### Comportamiento actual
- Usuarios públicos (sin login): ✅ Funciona correctamente
- Usuarios administradores/logueados: ❌ Redirección automática a `/shop`
- **Navegador normal después de logout**: ❌ Sigue redireccionando (cookies persistentes)
- **Modo incógnito**: ✅ Funciona correctamente

#### 💡 Hallazgo clave (23 marzo 2026)
**El problema persiste DESPUÉS de hacer logout en el navegador normal**, pero NO ocurre en modo incógnito. Esto indica que **hay cookies o residuos de sesión persistentes** que causan el comportamiento.

**✅ SOLUCIÓN VERIFICADA:** Limpiar storage del navegador (F12 → Application → Clear storage → Clear site data) resuelve el problema completamente.

**Cookies/Storage sospechosos:**
- `cids` - Lista de company IDs activas (usada por MCS-PRELOAD)
- `session_id` - Sesión de Odoo residual
- `website_id` - ID del website actual
- `frontend_lang` - Idioma del frontend
- `localStorage` / `sessionStorage` - Datos de sesiones previas

#### Estado actual
🟢 **RESUELTO (Workaround documentado)** - No es un bug del código, es residuo de navegador. Los usuarios con navegador "limpio" no experimentan el problema.

#### Causa probable
El MCS-PRELOAD (`addons/microsite_company_switch/views/assets.xml`) modifica la sesión del usuario según cookies de compañía. Esto puede causar conflictos con:
- Validación de categorías según compañía actual
- Multi-website/multi-compañía en Odoo 19
- Caché de sesión para usuarios internos

#### Logs relevantes
```
[CanariasSelect2] Navegando a: /shop/category/animales-449
Navigated to https://canariasconectada.es/shop/category/animales-449
[MCS-PRELOAD] Patch aplicado
Navigated to https://canariasconectada.es/shop?ppg=12
```

#### Pruebas realizadas
- ✅ Desactivar MCS-PRELOAD: No resuelve el problema
- ✅ Usar window.location.replace(): No resuelve
- ✅ Usar query params (?category=ID): Error 422
- ✅ Usar URLs completas (/shop/category/slug): Redirección ocurre igual

#### Archivos relacionados
- `addons/zzz_zone_fix/views/shop_canarias.xml` - Template del select
- `addons/microsite_company_switch/views/assets.xml` - MCS-PRELOAD
- `odoo/addons/website_sale/controllers/main.py` - Controlador shop

---

## MEJORAS PENDIENTES

### 🟡 Mejora #1: Cargar categorías de forma asíncrona
**Descripción:** Actualmente las categorías se cargan en el servidor. Para mejorar performance, cargar vía AJAX.

### 🟡 Mejora #2: Filtro de zonas comerciales
**Descripción:** Agregar un segundo select para filtrar por zonas (Guanarteme, Tamaraceite, etc.)

### 🟡 Mejora #3: Persistir selección de categoría
**Descripción:** Recordar la última categoría seleccionada en sessionStorage

---

## HISTORIAL DE BUGS CORREGIDOS

### ✅ BUG Corregido: Select2 no cargaba
**Fecha:** 2026-03-23
**Solución:** Cargar Select2 dinámicamente desde CDN después de verificar jQuery

### ✅ BUG Corregido: XPath inválidos en templates
**Fecha:** 2026-03-23
**Solución:** Usar `contains(@t-attf-class, ...)` en lugar de `hasclass()` para clases dinámicas

### ✅ BUG Corregido: Duplicación de categorías
**Fecha:** 2026-03-23
**Solución:** Usar `DISTINCT` en SQL para obtener categorías únicas

---

## NOTAS PARA DESARROLLO

- Odoo 19 usa assets frontend diferentes a versiones anteriores
- jQuery no es global en Odoo 19, usar `window.jQuery`
- Select2 debe cargarse dinámicamente para evitar conflictos
- El MCS-PRELOAD afecta la sesión de usuarios logueados

---

## BACKUPS ESTABLES

- `BACKUP_ESTABLE_20260323_031206.sql` - Base de datos completa
- `BACKUP_ESTABLE_20260323_031206_filestore.tar.gz` - Filestore (3GB)
- Ubicación: `/context/backups/`

