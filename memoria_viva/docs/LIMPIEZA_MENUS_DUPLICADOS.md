# Limpieza de Menús Duplicados - Memoria Viva

## 📋 Problema Detectado

**Fecha:** 7 de Abril de 2026  
**Síntoma:** Menús de Memoria Viva aparecían duplicados en el menú principal de Odoo

### Descripción

Los menús antiguos de la versión anterior del módulo seguían apareciendo directamente en el menú principal de Odoo, junto al nuevo menú organizado. Esto causaba confusión y duplicación de opciones.

### Menús Problemáticos

Los siguientes menús aparecían en el menú principal (sin parent):

| ID | Nombre | Secuencia |
|----|--------|-----------|
| 446 | Lugares | 10 |
| 461 | Jerarquía de Categorías | 20 |
| 465 | Tags y Clasificaciones | 30 |

Y sus menús hijos:

| ID | Nombre | Parent ID |
|----|--------|-----------|
| 462 | Tipos | 461 |
| 463 | Categorías | 461 |
| 464 | Subcategorías | 461 |
| 466 | Público Objetivo | 465 |
| 467 | Momento del Día | 465 |
| 468 | Ambientes | 465 |
| 469 | Experiencias | 465 |
| 470 | Fiestas/Eventos | 465 |

---

## 🔧 Solución Aplicada

### Comando SQL de Limpieza

```sql
-- Eliminar menús hijos primero (por restricción de clave foránea)
DELETE FROM ir_ui_menu WHERE parent_id IN (446, 461, 465);

-- Eliminar menús padres huérfanos
DELETE FROM ir_ui_menu WHERE id IN (446, 461, 465);
```

### Resultado

- ✅ **8 menús hijos** eliminados
- ✅ **3 menús padres** eliminados
- ✅ **Total: 11 menús antiguos** removidos

---

## ✅ Estado Final del Menú

Después de la limpieza, el menú quedó organizado correctamente:

```
MENÚ PRINCIPAL DE ODOO
│
└── Memoria Viva (único menú raíz)
    ├── 📄 Contenido
    │   ├── Lugares
    │   ├── Eventos
    │   └── Anuncios
    ├── 🏷️ Clasificación
    │   ├── Tipos
    │   ├── Categorías
    │   ├── Subcategorías
    │   └── Tags
    ├── 🛡️ Moderación
    │   ├── Comentarios
    │   └── Palabras Prohibidas
    └── ⚙️ Configuración
        └── Ajustes Generales
```

**Ya NO aparecen en el menú principal:**
- ❌ Lugares (huérfano)
- ❌ Jerarquía de Categorías (huérfano)
- ❌ Tags y Clasificaciones (huérfano)

---

## 🔍 Verificación

### Consulta SQL de Verificación

```sql
-- Verificar menús huérfanos de Memoria Viva
SELECT 
    id,
    name->>'en_US' as name,
    parent_id,
    sequence
FROM ir_ui_menu
WHERE name->>'en_US' IN (
    'Lugares', 'Eventos', 'Anuncios', 'Configuración',
    'Tipos', 'Categorías', 'Subcategorías', 'Tags',
    'Moderación', 'Comentarios', 'Palabras Prohibidas'
)
ORDER BY parent_id NULLS FIRST, sequence;
```

### Resultado Esperado

Todos los menús deben tener `parent_id` asignado (no NULL), excepto "Memoria Viva" que es el menú raíz.

---

## 📝 Notas

1. **Los menús nuevos** (IDs 573-590) están correctamente anidados bajo "Memoria Viva"
2. **Los menús antiguos** (IDs 446-470) fueron completamente eliminados
3. **No afecta datos:** Solo se eliminaron registros de `ir_ui_menu`, los datos del módulo permanecen intactos

---

## 🔄 Rollback (si es necesario)

Si se necesita restaurar los menús antiguos, restaurar desde el backup:

```bash
# Restaurar backup completo
sudo -u postgres psql canarias_conectada < /home/odoo/backup/memoria_viva_pre_fix_20260407_051448.sql
```

O crear los menús manualmente desde la interfaz de Odoo.

---

**Fecha de corrección:** 2026-04-07  
**Ejecutado por:** Sistema de mantenimiento  
**Estado:** ✅ Resuelto
