# Índice de Tests - Lugares de Interés

## Tests Unitarios (Odoo)

Ubicación: `/home/odoo/addons/lugares_interes/tests/`

### test_lugares_interes_models.py
**Ruta**: `tests/test_lugares_interes_models.py`

Tests para modelos principales del sistema.

**Cobertura**:
- Creación de lugares (historias)
- Generación de slugs únicos
- Workflow de aprobación/rechazo
- Contadores de likes y vistas
- Permisos de acceso
- Configuración por website

**Ejecución**:
```bash
./odoo-bin -i lugares_interes -d canarias_conectada --test-enable \
  --test-tags=lugares_interes --stop-after-init
```

---

### test_lugares_interes_comentarios.py
**Ruta**: `tests/test_lugares_interes_comentarios.py`

Tests específicos del sistema de comentarios.

**Cobertura**:
- Creación de comentarios
- Moderación automática
- Detección de palabras prohibidas
- Respuestas anidadas
- Aprobación/rechazo manual
- Permisos de edición

**Tests incluidos**:
| Test | Descripción |
|------|-------------|
| test_01_crear_comentario_simple | Creación básica |
| test_02_comentario_aprobado_por_defecto | Auto-aprobación |
| test_03_comentario_pendiente_con_palabra_prohibida | Moderación |
| test_04_comentario_case_insensitive | Case insensitive |
| test_06_crear_respuesta | Respuestas anidadas |
| test_07_comentario_tiene_respuestas | Flag de respuestas |
| test_08_maximo_nivel_anidamiento | Límite nivel 1 |
| test_09_aprobar_comentario | Aprobación manual |
| test_10_rechazar_comentario | Rechazo |

---

### test_lugares_interes_website.py
**Ruta**: `tests/test_lugares_interes_website.py`

Tests para controladores web y API.

**Cobertura**:
- Páginas frontend accesibles
- Endpoints API
- XML-RPC
- Permisos de acceso web

**Tests incluidos**:
| Test | Descripción |
|------|-------------|
| test_01_pagina_listado_accesible | Listado público |
| test_02_pagina_detalle_accesible | Detalle público |
| test_05_api_submit_lugar | API de envío |
| test_08_api_like_lugar | Sistema de likes |
| test_11_api_enviar_comentario_logueado | API comentarios |
| test_01_xmlrpc_search_read_lugares | XML-RPC básico |

---

## Tests Standalone (Scripts)

Ubicación: `/home/odoo/addons/lugares_interes/scripts/tests/`

### test_comentarios_frontend.py
**Ruta**: `scripts/tests/test_comentarios_frontend.py`

Test completo que valida todo el sistema.

**Ventajas**:
- No requiere reiniciar Odoo
- Más rápido que tests unitarios
- Valida frontend, API y backend en uno

**Resultados esperados**:
```
✅ Tests pasados: 18/18
❌ Tests fallidos: 0/18
📊 Tasa de éxito: 100.0%
```

**Ejecución**:
```bash
cd /home/odoo
python3 addons/lugares_interes/scripts/tests/test_comentarios_frontend.py
```

---

### test_xmlrpc.py
**Ruta**: `scripts/tests/test_xmlrpc.py`

Tests de integración vía XML-RPC.

**Uso**:
```bash
python3 addons/lugares_interes/scripts/tests/test_xmlrpc.py \
  http://localhost:8069 canarias_conectada admin admin
```

---

### test_orm.py
**Ruta**: `scripts/tests/test_orm.py`

Tests directos al ORM.

**Uso**:
```bash
python3 addons/lugares_interes/scripts/tests/test_orm.py
```

---

## Estrategia de Testing

### Flujo Recomendado

1. **Desarrollo**: Usar scripts standalone para pruebas rápidas
2. **Pre-commit**: Ejecutar tests unitarios de Odoo
3. **CI/CD**: Tests unitarios completos
4. **Producción**: Validación con script frontend

### Cobertura

| Componente | Tests Unitarios | Scripts | Total |
|------------|-----------------|---------|-------|
| Modelos | ✅ | ✅ | 20+ |
| API | ✅ | ✅ | 10+ |
| Frontend | ❌ | ✅ | 7 |
| Integración | ❌ | ✅ | 3 |

---

## Resultados Históricos

### Última Ejecución: 6 de abril de 2026

```
============================================================
🚀 INICIANDO TESTS DE SISTEMA DE COMENTARIOS
============================================================

🧪 TESTS DE FRONTEND (Páginas Web) - 7/7 ✅
🧪 TESTS DE API (Endpoints) - 2/2 ✅
🧪 TESTS DE BACKEND (Modelos) - 9/9 ✅

============================================================
✅ Tests pasados: 18/18
❌ Tests fallidos: 0/18
📊 Tasa de éxito: 100.0%
============================================================
```

---

## Troubleshooting

### Tests fallan con "database not found"
Verificar que el usuario tenga permisos sobre la base de datos.

### Tests de Odoo no se ejecutan
Asegurar de usar `--test-enable` y `--test-tags=lugares_interes`.

### Scripts standalone fallan
Verificar que Odoo esté corriendo y accesible.

---

## Ver Resultados

Los resultados de tests se guardan en:
- `/home/odoo/TEST_RESULTS.md`
- `/home/odoo/addons/lugares_interes/docs/tests/RESULTADOS.md`
