# Guía de Pruebas - Memoria Viva

## Resumen de Implementación

### Archivos Creados/Modificados

#### Tests Automatizados
1. `tests/__init__.py` - Inicializador del paquete de tests
2. `tests/test_memoria_viva_models.py` - Tests para modelos (lugares, likes, configuración)
3. `tests/test_memoria_viva_comentarios.py` - Tests para sistema de comentarios
4. `tests/test_memoria_viva_website.py` - Tests para controladores web
5. `scripts/test_xmlrpc.py` - Script de prueba XML-RPC
6. `scripts/test_orm.py` - Script de prueba ORM directo

#### JavaScript Frontend
- `static/src/js/memoria_viva_comments.js` - Sistema de comentarios completo

#### Correcciones Realizadas
- `__manifest__.py` - Corregida referencia al archivo JS
- `views/memoria_viva_templates.xml` - Template limpio sin código residual

---

## Pruebas Manuales desde Interfaz Web

### 1. Prueba de Listado de Lugares
**URL:** `https://guanarteme.canariasconectada.es/memoria-viva`

**Verificar:**
- [ ] Se carga la página sin errores 500
- [ ] Se muestran los lugares aprobados
- [ ] Funciona el buscador
- [ ] Funcionan los filtros por tipo y categoría
- [ ] Los likes se pueden dar y persisten

### 2. Prueba de Detalle de Lugar
**URL:** `https://guanarteme.canariasconectada.es/memoria-viva/<slug>`

**Verificar:**
- [ ] Se carga la página sin errores 500
- [ ] Se muestra la información del lugar
- [ ] Se muestra el contador de likes
- [ ] Sección de comentarios visible (si está habilitada)

### 3. Prueba de Comentarios

#### 3.1 Como Usuario Anónimo
- [ ] Ver que aparece mensaje "Inicia sesión para comentar"
- [ ] No debe poder enviar comentarios

#### 3.2 Como Usuario Logueado
- [ ] Formulario de comentario visible
- [ ] Puede enviar comentario
- [ ] Comentario aparece inmediatamente si no tiene palabras prohibidas
- [ ] Comentario con palabra prohibida queda pendiente

#### 3.3 Respuestas a Comentarios
- [ ] Botón "Responder" visible en comentarios
- [ ] Puede responder a un comentario
- [ ] Respuesta aparece anidada

### 4. Prueba Backend (Administración)

#### 4.1 Gestión de Comentarios
**Ruta:** `Aplicaciones > Memoria Viva > Comentarios`

**Verificar:**
- [ ] Lista de comentarios con filtros (aprobado/pendiente/rechazado)
- [ ] Puede aprobar comentario pendiente
- [ ] Puede rechazar comentario
- [ ] Notificación/email enviado al aprobar/rechazar

#### 4.2 Gestión de Palabras Prohibidas
**Ruta:** `Aplicaciones > Memoria Viva > Palabras Prohibidas`

**Verificar:**
- [ ] Puede agregar nueva palabra prohibida
- [ ] Puede desactivar palabra sin eliminarla
- [ ] Comentarios con palabras prohibidas quedan pendientes

---

## Pruebas XML-RPC

Las siguientes pruebas pueden realizarse con el script `scripts/test_xmlrpc.py`:

```bash
# Ejecutar todas las pruebas XML-RPC
python3 addons/memoria_viva/scripts/test_xmlrpc.py

# Con credenciales personalizadas
python3 addons/memoria_viva/scripts/test_xmlrpc.py http://localhost:8069 canarias_conectada admin admin
```

**Funcionalidades probadas:**
1. Crear lugar via API
2. Leer datos de lugar
3. Buscar lugares
4. Actualizar lugar
5. Crear like
6. Crear comentario
7. Listar comentarios
8. Aprobar comentario
9. Crear palabra prohibida
10. Obtener configuración

---

## Pruebas ORM (Python)

```bash
# Ejecutar pruebas ORM directas
python3 addons/memoria_viva/scripts/test_orm.py
```

**Funcionalidades probadas:**
1. Crear lugar
2. Leer lugar
3. Actualizar lugar
4. Crear like
5. Crear comentario
6. Aprobar comentario
7. Crear respuesta
8. Crear palabra prohibida

---

## Solución de Problemas

### Error: Modelos no registrados
Si los modelos `memoria.viva.comentario` y `memoria.viva.palabra.prohibida` no aparecen:

```sql
-- Verificar en base de datos
SELECT model FROM ir_model WHERE model LIKE 'memoria.viva%';

-- Si faltan, forzar actualización del módulo
UPDATE ir_module_module SET state='to upgrade' WHERE name='memoria_viva';
```

Luego reiniciar Odoo con `-u memoria_viva`

### Error: Tablas no creadas
```sql
-- Verificar tablas
SELECT table_name FROM information_schema.tables 
WHERE table_schema='public' AND table_name LIKE 'memoria%';
```

Si faltan tablas de comentarios, ejecutar:
```bash
./odoo-bin -u memoria_viva -d canarias_conectada --stop-after-init
```

---

## Verificación de Tests Unitarios

Para ejecutar los tests unitarios de Odoo:

```bash
./odoo-bin -i memoria_viva -d canarias_conectada --test-enable \
    --stop-after-init --test-tags=memoria_viva
```

### Tests Incluidos:

#### test_memoria_viva_models.py
- `test_01_crear_lugar` - Creación básica
- `test_02_slug_unico` - Unicidad de slug
- `test_03_aprobar_lugar` - Workflow de aprobación
- `test_04_rechazar_lugar` - Rechazo de lugar
- `test_05_incrementar_contador_vistas` - Contador de vistas
- `test_06_like_count_computation` - Computación de likes
- `test_07_compute_ubicacion` - Coordenadas
- `test_08_permiso_lectura_publico` - Permisos públicos
- `test_09_permiso_escritura_admin` - Permisos admin
- `test_10_configuracion_por_website` - Configuración
- `test_12_crear_like` - Sistema de likes
- `test_13_like_unico_por_sesion` - Prevención de likes duplicados

#### test_memoria_viva_comentarios.py
- `test_01_crear_comentario_simple` - Creación básica
- `test_02_comentario_aprobado_por_defecto` - Auto-aprobación
- `test_03_comentario_pendiente_con_palabra_prohibida` - Moderación
- `test_04_comentario_case_insensitive` - Case insensitive
- `test_06_crear_respuesta` - Respuestas anidadas
- `test_07_comentario_tiene_respuestas` - Flag de respuestas
- `test_08_maximo_nivel_anidamiento` - Límite de anidamiento
- `test_09_aprobar_comentario` - Aprobación manual
- `test_10_rechazar_comentario` - Rechazo
- `test_11_get_comentarios_aprobados` - Listado público
- `test_14_autor_nombre_computado` - Autor
- `test_16_crear_palabra_prohibida` - Gestión de palabras

#### test_memoria_viva_website.py
- `test_01_pagina_listado_accesible` - Página pública
- `test_02_pagina_detalle_accesible` - Detalle público
- `test_05_api_submit_lugar` - API de envío
- `test_08_api_like_lugar` - API de likes
- `test_11_api_enviar_comentario_logueado` - API comentarios
- `test_13_api_listar_comentarios` - API listado
- `test_14_api_comentario_con_moderacion` - API moderación
- `test_01_xmlrpc_search_read_lugares` - XML-RPC básico

---

## Estado Actual

### ✅ Implementado y Funcionando
1. **Frontend JavaScript** - `memoria_viva_comments.js` completo
2. **Templates** - Limpios y funcionales
3. **Tests** - Suite completa de pruebas
4. **Scripts** - XML-RPC y ORM para verificación

### ⚠️ Requiere Atención
Los modelos `memoria.viva.comentario` y `memoria.viva.palabra.prohibida` pueden requerir:
- Reinicio de Odoo con `-u memoria_viva`
- O actualización forzada desde línea de comandos

### Próximos Pasos Recomendados
1. Reiniciar el servidor Odoo con actualización forzada
2. Verificar en el backend que los modelos aparezcan
3. Probar el envío de comentarios desde el frontend
4. Verificar la moderación automática

---

## Contacto y Soporte

Para problemas técnicos:
1. Revisar logs de Odoo: `/home/odoo/logs/`
2. Verificar estado del módulo en base de datos
3. Ejecutar scripts de prueba para diagnóstico
