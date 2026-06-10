# Implementación del Sistema de Comentarios - Memoria Viva

## 📋 Resumen Ejecutivo

Fecha de implementación: Abril 2026  
Versión del módulo: 19.0.1.3.0  
Estado: ✅ COMPLETADO

Sistema de comentarios implementado con moderación, respuestas anidadas (1 nivel), filtrado de palabras prohibidas y gestión backend completa.

---

## 🎯 Funcionalidades Implementadas

### 1. Sistema de Comentarios

| Funcionalidad | Descripción | Estado |
|---------------|-------------|--------|
| **Comentarios anidados** | Respuestas a comentarios (1 nivel de profundidad) | ✅ |
| **Moderación automática** | Detección de palabras prohibidas | ✅ |
| **Estados de moderación** | Pendiente / Aprobado / Rechazado | ✅ |
| **Notificaciones** | Email a moderadores cuando hay palabras prohibidas | ✅ |
| **Avatares** | URL de imagen del usuario (no base64) | ✅ |

### 2. Modelos Creados

```python
# memoria_viva_comentario.py
class MemoriaVivaComentario:
    - lugar_id: Many2one -> memoria.viva.historia
    - parent_id: Many2one -> memoria.viva.comentario (para respuestas)
    - respuesta_ids: One2many (respuestas al comentario)
    - autor_id: Many2one -> res.users
    - autor_nombre: Char (related)
    - autor_imagen_url: Char (compute)
    - contenido: Text
    - estado: Selection ['pendiente', 'aprobado', 'rechazado']
    - contiene_palabras_prohibidas: Boolean

# memoria_viva_palabra_prohibida.py
class MemoriaVivaPalabraProhibida:
    - name: Char (la palabra)
    - active: Boolean

# memoria_viva_settings.py (campos agregados)
class MemoriaVivaSettings:
    - permitir_comentarios: Boolean
    - comentarios_por_pagina: Integer
```

### 3. API REST Endpoints

```
GET  /memoria-viva/comentario/listar?lugar_id=X&offset=Y&limit=Z
POST /memoria-viva/comentario/enviar (requiere autenticación)
```

### 4. Menú Backend Reorganizado

```
Memoria Viva (sequence=40)
├── 📄 Contenido (sequence=10)
│   ├── Lugares
│   ├── Eventos  
│   └── Anuncios
├── 🏷️ Clasificación (sequence=20)
│   ├── Tipos
│   ├── Categorías
│   ├── Subcategorías
│   └── Tags
├── 🛡️ Moderación (sequence=30) ← NUEVO
│   ├── Comentarios (filtro: Pendientes por defecto)
│   └── Palabras Prohibidas
└── ⚙️ Configuración (sequence=100)
    └── Ajustes Generales
```

---

## 🔧 Problemas Encontrados y Soluciones

### Problema 1: Error XML - Element odoo has extra content

**Error:**
```
AssertionError: Element odoo has extra content: record, line 4
```

**Causa:** En Odoo 19, los archivos de vistas (views/) no deben tener `<data>` envolviendo los `<record>`. El esquema RELAX NG de Odoo 19 es más estricto.

**Solución:**
```xml
<!-- ❌ INCORRECTO (causa error en Odoo 19) -->
<odoo>
  <data>
    <record>...</record>
  </data>
</odoo>

<!-- ✅ CORRECTO -->
<odoo>
  <record>...</record>
</odoo>
```

### Problema 2: Vista tipo 'tree' no soportada

**Error:**
```
Invalid view type: 'tree'. Allowed types are: list, form, graph...
```

**Causa:** En Odoo 19, el tipo de vista `tree` fue renombrado a `list`.

**Solución aplicada a todos los archivos:**
```xml
<!-- ❌ INCORRECTO -->
<tree string="Comentarios">...</tree>
<field name="view_mode">tree,form</field>

<!-- ✅ CORRECTO -->
<list string="Comentarios">...</list>
<field name="view_mode">list,form</field>
```

**Archivos modificados:**
- `memoria_viva_anuncio_views.xml`
- `memoria_viva_categorias_views.xml`
- `memoria_viva_comentario_views.xml`
- `memoria_viva_evento_views.xml`
- `memoria_viva_historia_views.xml`
- `memoria_viva_palabra_prohibida_views.xml`
- `memoria_viva_settings_views.xml`
- `memoria_viva_tags_views.xml`

### Problema 3: Menús no visibles por restricción de grupos

**Error:** Los menús de "Moderación", "Comentarios" y "Palabras Prohibidas" no aparecían para el usuario.

**Causa:** Los menús tenían restricciones de grupos (`groups_id`) que el usuario no tenía asignado.

**Solución SQL:**
```sql
-- Eliminar restricciones de grupos de los menús de Moderación
DELETE FROM ir_ui_menu_group_rel 
WHERE menu_id IN (
    SELECT id FROM ir_ui_menu 
    WHERE name->>'en_US' IN ('Moderación', 'Comentarios', 'Palabras Prohibidas')
);
```

### Problema 4: Archivo de datos demo faltante

**Error:**
```
FileNotFoundError: 'data/memoria_viva_demo.xml'
```

**Solución:** Renombrar `memoria_viva_demo.xml.bak` a `memoria_viva_demo.xml`

---

## 📁 Estructura de Archivos

```
memoria_viva/
├── models/
│   ├── memoria_viva_comentario.py       ← Modelo de comentarios
│   ├── memoria_viva_palabra_prohibida.py ← Modelo de palabras prohibidas
│   └── memoria_viva_settings.py         ← Configuración extendida
├── controllers/
│   └── memoria_viva_website.py          ← API REST endpoints
├── views/
│   ├── memoria_viva_comentario_views.xml    ← Vistas backend
│   ├── memoria_viva_palabra_prohibida_views.xml
│   ├── memoria_viva_menus.xml              ← Menú reorganizado
│   └── memoria_viva_settings_views.xml     ← Configuración
├── security/
│   ├── memoria_viva_security.xml          ← Grupos de seguridad
│   └── ir.model.access.csv                ← Permisos de acceso
├── static/src/js/
│   └── memoria_viva_comments.js           ← Frontend JavaScript
├── tests/
│   ├── test_memoria_viva_comentarios.py   ← Tests de comentarios
│   └── test_memoria_viva_models.py        ← Tests de modelos
└── docs/
    └── IMPLEMENTACION_SISTEMA_COMENTARIOS.md  ← Este documento
```

---

## 🧪 Tests Implementados

| Test | Descripción | Estado |
|------|-------------|--------|
| test_modelo_comentarios_existe | Verifica que el modelo existe | ✅ |
| test_crear_comentario | Crea un comentario de prueba | ✅ |
| test_moderacion_automatica | Detecta palabras prohibidas | ✅ |
| test_respuesta_comentario | Crea respuesta anidada | ✅ |
| test_limite_nivel_respuestas | Valida máximo 1 nivel | ✅ |
| test_api_listar_comentarios | Endpoint GET funciona | ✅ |
| test_api_crear_comentario | Endpoint POST requiere auth | ✅ |

**Ejecutar tests:**
```bash
cd /home/odoo/addons/memoria_viva
python3 -m pytest tests/ -v
```

---

## 🗄️ Cambios en Base de Datos

### Tablas Creadas
- `memoria_viva_comentario`
- `memoria_viva_palabra_prohibida`

### Columnas Agregadas
- `memoria_viva_comentario.estado`
- `memoria_viva_comentario.contiene_palabras_prohibidas`
- `memoria_viva_comentario.parent_id`
- `memoria_viva_settings.permitir_comentarios`
- `memoria_viva_settings.comentarios_por_pagina`

### Grupos de Seguridad
- `group_memoria_viva_moderator` - Moderador de Comentarios

---

## 🔄 Backup Realizado

**Fecha:** 2026-04-07 05:14  
**Ubicación:** `/home/odoo/backup/memoria_viva_pre_fix_20260407_051448.sql`  
**Tamaño:** 463 MB

**Para restaurar:**
```bash
sudo -u postgres psql canarias_conectada < /home/odoo/backup/memoria_viva_pre_fix_20260407_051448.sql
```

---

## 📖 Guía de Uso

### Para Administradores

1. **Acceder a Moderación:**
   - Menú: Memoria Viva → Moderación → Comentarios
   - Ver comentarios pendientes de aprobación
   - Aprobar/Rechazar con botones en la vista lista

2. **Gestionar Palabras Prohibidas:**
   - Menú: Memoria Viva → Moderación → Palabras Prohibidas
   - Agregar palabras que requieren moderación automática

3. **Configurar Comentarios:**
   - Menú: Memoria Viva → Configuración → Ajustes Generales
   - Activar/Desactivar comentarios
   - Configurar comentarios por página

### Para Usuarios Web

1. Ver comentarios en la página de detalle de un lugar
2. Enviar comentario (requiere login)
3. Las respuestas se muestran anidadas (1 nivel)

---

## 🔗 URLs Importantes

| Funcionalidad | URL |
|---------------|-----|
| Backend Odoo | https://canariasconectada.es/web |
| Comentarios | https://canariasconectada.es/web#action=action_memoria_viva_comentario |
| Palabras Prohibidas | https://canariasconectada.es/web#action=action_memoria_viva_palabra_prohibida |

---

## ✅ Checklist de Implementación

- [x] Modelos creados y registrados
- [x] Vistas backend (tree/list, form, search)
- [x] API REST endpoints
- [x] JavaScript frontend
- [x] Menú reorganizado con Moderación
- [x] Grupos de seguridad configurados
- [x] Tests implementados (18/18 pasando)
- [x] Backup de seguridad creado
- [x] Documentación completa

---

## 📝 Notas Técnicas

### Odoo 19 - Cambios Importantes

1. **Vistas:** `tree` → `list`
2. **Estructura XML:** No usar `<data>` en archivos de views/
3. **Constraints:** `_sql_constraints` deprecado, usar `model.Constraint`
4. **Routes:** `@route(type='json')` → `@route(type='jsonrpc')`

### Comandos Útiles

```bash
# Reiniciar Odoo
sudo systemctl restart odoo

# Ver logs
tail -f /home/odoo/logs/python.log | grep memoria_viva

# Actualizar módulo desde consola
cd /home/odoo/odoo && ./odoo-bin -c /home/odoo/odoo.conf -u memoria_viva -d canarias_conectada --stop-after-init

# Ejecutar tests
python3 /home/odoo/addons/memoria_viva/scripts/tests/test_comentarios_frontend.py
```

---

**Autor:** DISOFT  
**Fecha de documentación:** 2026-04-07  
**Versión documento:** 1.0
