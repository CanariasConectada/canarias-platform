# Incidente Resuelto: Errores 404, 500 y Comentarios No Visibles

**Fecha:** 2026-04-07  
**Módulo:** lugares_interes  
**Versión:** 19.0.1.3.0  
**Estado:** ✅ RESUELTO

---

## Resumen Ejecutivo

Se identificaron y resolvieron tres problemas críticos en el módulo Lugares de Interés:

1. **Error 404** al acceder a lugares desde el dominio principal
2. **Comentarios no visibles** para usuarios anónimos
3. **Error 500 (Internal Server Error)** en páginas de detalle

---

## Problema 1: Error 404 - Lugar No Encontrado

### Síntoma
Al acceder a `https://canariasconectada.es/lugares-de-interes/mirador-las-coloradas` se obtenía un error 404.

### Causa Raíz
El lugar "Mirador Las Coloradas" estaba configurado con:
- `website_primario_id`: 229 (Zona Comercial Guanarteme)
- Dominio: `guanarteme.canariasconectada.es`

Pero el usuario intentaba acceder desde el dominio principal `canariasconectada.es` (website 228).

El controlador verifica que el lugar pertenezca al website actual:
```python
domain = [
    ('slug', '=', slug),
    ('state', '=', 'aprobado'),
    '|',
    ('website_primario_id', '=', request.website.id),
    ('website_ids', 'in', [request.website.id])
]
```

### Solución
Acceder al lugar desde la URL correcta del micrositio:
```
https://guanarteme.canariasconectada.es/lugares-de-interes/mirador-las-coloradas
```

### Verificación
```sql
SELECT id, name, slug, state, website_primario_id 
FROM lugares_interes_historia 
WHERE slug = 'mirador-las-coloradas';
```

Resultado:
```
 id |         name          |         slug          |  state   | website_primario_id 
----+-----------------------+-----------------------+----------+---------------------
  3 | Mirador Las Coloradas | mirador-las-coloradas | aprobado |                 229
```

---

## Problema 2: Comentarios No Visibles para Usuarios Anónimos

### Síntoma
Los usuarios no logueados no podían ver los comentarios, a pesar de que la configuración `comentarios_publicos` estaba activada.

### Causa Raíz (Fase 1)
El campo `comentarios_publicos` en `lugares_interes_settings` estaba en `false` (valor por defecto).

### Solución (Fase 1)
Activar la configuración en la base de datos:
```sql
UPDATE lugares_interes_settings 
SET comentarios_publicos = true;
```

### Causa Raíz (Fase 2)
Después de activar la configuración, los comentarios seguían sin verse. El problema estaba en el JavaScript (`lugares_interes_comments.js`):

```javascript
var lugarIdInput = document.querySelector('input[name="lugar_id"]');
if (!lugarIdInput || !lista) return;  // Se detenía aquí para usuarios anónimos
```

El input `lugar_id` solo existía dentro del formulario de comentarios, que **solo se renderiza para usuarios logueados**. Para usuarios anónimos, el input no existía y el JavaScript salía sin cargar los comentarios.

### Solución (Fase 2)

#### Cambio 1: Template XML
Agregar un input hidden accesible para todos los usuarios:
```xml
<!-- Input oculto con lugar_id (accesible para todos) -->
<input type="hidden" id="lugar_id" name="lugar_id" t-att-value="lugar.id"/>

<!-- Lista de comentarios -->
<div id="comentarios-lista">
```

**Archivo:** `views/lugares_interes_templates.xml`

#### Cambio 2: JavaScript
Actualizar el selector para buscar ambos inputs:
```javascript
var lugarIdInput = document.getElementById('lugar_id') || 
                   document.querySelector('input[name="lugar_id"]');
```

**Archivo:** `static/src/js/lugares_interes_comments.js`

### Resultado Esperado
- ✅ Usuarios anónimos: Pueden **ver** comentarios aprobados
- ❌ Usuarios anónimos: No pueden publicar comentarios (botón "Iniciar sesión")
- ✅ Usuarios logueados: Pueden **ver** y **publicar** comentarios

---

## Problema 3: Error 500 (Internal Server Error)

### Síntoma
Al intentar acceder a cualquier página de detalle de lugar, se obtenía:
```
Internal Server Error
The server encountered an internal error and was unable to complete your request.
```

### Causa Raíz
Existían **vistas duplicadas** de "Lugares de Interés - Detalle" en la base de datos:

```sql
SELECT id, name, arch_db IS NULL as arch_is_null, arch_fs
FROM ir_ui_view 
WHERE name = 'Lugares de Interés - Detalle';
```

Resultado:
```
  id   |          name          | arch_is_null |                    arch_fs                    
-------+------------------------+--------------+-----------------------------------------------
 11526 | Lugares de Interés - Detalle | t            |                                               
 11548 | Lugares de Interés - Detalle | f            | lugares_interes/views/lugares_interes_templates.xml 
```

La vista con ID 11526 tenía `arch_db = NULL`, causando el error:
```
ValueError: can only parse strings
File ".../ir_ui_view.py", line 1003, in _combine
    combined_arch = etree.fromstring(self.arch)
```

### Solución
Eliminar la vista defectuosa (con arch_db NULL):
```sql
DELETE FROM ir_ui_view 
WHERE name = 'Lugares de Interés - Detalle'
AND arch_db IS NULL;
```

Luego reiniciar Odoo:
```bash
sudo systemctl restart odoo
```

### Prevención
Para evitar vistas duplicadas en el futuro, se recomienda:
1. Usar siempre `xml_id` únicos en los archivos XML
2. Evitar crear vistas manualmente desde la interfaz de Odoo
3. Cuando se actualiza un módulo, verificar que no queden vistas huérfanas

---

## Configuración Final

### Base de Datos - Settings
```sql
SELECT 
    permitir_comentarios,      -- true
    comentarios_publicos,      -- true
    comentarios_por_pagina     -- 10
FROM lugares_interes_settings;
```

### API de Comentarios (Prueba)
```bash
curl "https://guanarteme.canariasconectada.es/lugares-de-interes/comentario/listar?lugar_id=3"
```

Respuesta esperada:
```json
{
    "success": true,
    "comentarios": [
        {
            "id": 48,
            "autor_nombre": "Domingo Santana Santana | ABinformática",
            "autor_imagen_url": "...",
            "contenido": "Hola mundo!!",
            "fecha": "06/04/2026 21:52",
            "respuestas": []
        }
    ],
    "total": 1,
    "tiene_mas": false
}
```

---

## Archivos Modificados

1. **`views/lugares_interes_templates.xml`**
   - Agregado input `#lugar_id` fuera del bloque condicional de usuarios logueados

2. **`static/src/js/lugares_interes_comments.js`**
   - Actualizado selector para buscar input por ID y por name

3. **Base de datos:**
   - Actualizado `comentarios_publicos` a `true`
   - Eliminadas vistas duplicadas con `arch_db` en NULL

---

## Testing

### Escenario 1: Usuario Anónimo
1. Abrir navegador en modo incógnito
2. Acceder a: https://guanarteme.canariasconectada.es/lugares-de-interes/mirador-las-coloradas
3. ✅ Debe ver el detalle del lugar
4. ✅ Debe ver los comentarios existentes
5. ✅ Debe ver botón "Iniciar sesión para comentar"
6. ❌ No debe ver formulario de comentarios

### Escenario 2: Usuario Logueado
1. Iniciar sesión en el sistema
2. Acceder a: https://guanarteme.canariasconectada.es/lugares-de-interes/mirador-las-coloradas
3. ✅ Debe ver el detalle del lugar
4. ✅ Debe ver los comentarios existentes
5. ✅ Debe ver formulario para dejar comentario
6. ✅ Puede publicar comentarios

### Escenario 3: API Directa
```bash
# Sin autenticación (anónimo)
curl "https://guanarteme.canariasconectada.es/lugares-de-interes/comentario/listar?lugar_id=3"
# Debe retornar comentarios (comentarios_publicos=true)
```

---

## Rollback

Si es necesario revertir los cambios:

### Revertir Configuración
```sql
UPDATE lugares_interes_settings 
SET comentarios_publicos = false;
```

### Revertir Código
```bash
cd /home/odoo/addons/lugares_interes
git checkout -- views/lugares_interes_templates.xml
git checkout -- static/src/js/lugares_interes_comments.js
```

### Restaurar Backup
```bash
sudo -u postgres psql -d canarias_conectada < /home/odoo/backup/pre_deploy_20260407_071812.sql
```

---

## Lecciones Aprendidas

1. **Vistas duplicadas:** Cuando Odoo actualiza un módulo, si hay vistas sin `arch_fs` definido, pueden quedar huérfanas y causar errores.

2. **JavaScript y usuarios anónimos:** Los elementos del DOM que necesita el JS deben estar disponibles para todos los tipos de usuarios, no solo para los logueados.

3. **Configuración por defecto:** Los campos booleanos nuevos deben tener un valor por defecto explícito y documentado.

4. **Testing multi-rol:** Siempre probar funcionalidades tanto con usuarios logueados como anónimos.

---

## Referencias

- [Lugares de Interés - README](../README.md)
- [Documentación de API](./api/ENDPOINTS.md)
- [Guía de Testing](./guia_testing.md)

---

**Resuelto por:** Sistema de Soporte  
**Fecha de resolución:** 2026-04-07  
**Tiempo de resolución:** ~2 horas
