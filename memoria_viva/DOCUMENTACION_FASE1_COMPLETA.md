# Documentación Completa - Fase 1 Memoria Viva

**Fecha:** 2026-04-08  
**Versión:** 19.0.2.0.0  
**Estado:** ✅ COMPLETADO Y FUNCIONANDO EN PRODUCCIÓN

---

## Índice

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Cambios Realizados](#2-cambios-realizados)
3. [Problemas Encontrados y Soluciones](#3-problemas-encontrados-y-soluciones)
4. [Validación y Testing](#4-validación-y-testing)
5. [Archivos Modificados](#5-archivos-modificados)
6. [Backups](#6-backups)
7. [Próximos Pasos](#7-próximos-pasos)

---

## 1. Resumen Ejecutivo

### Objetivo de la Fase 1
Implementar mejoras en el frontend de Memoria Viva incluyendo:
- Campo DNI simplificado
- Cambio de colores a azul corporativo
- Checkbox de políticas obligatorio
- Reorganización del formulario
- Imagen de fondo en hero
- Sección editable con Website Builder
- Nuevas categorías
- Anti-spam básico

### Resultado
✅ Todos los objetivos completados. El sistema está funcionando en producción.

---

## 2. Cambios Realizados

### 2.1 Campo DNI Simplificado

**Descripción:** Campo de texto simple para documento de identidad sin validaciones complejas de formato.

**Implementación:**
- **Backend (models/memoria_viva_historia.py):**
```python
dni_remitente = fields.Char(
    string='Documento de identidad',
    required=True,
)

@api.constrains('dni_remitente')
def _check_dni_length(self):
    """Validar longitud 5-20 caracteres"""
    for record in self:
        if record.dni_remitente:
            if len(record.dni_remitente) < 5 or len(record.dni_remitente) > 20:
                raise ValidationError(_('El documento debe tener entre 5 y 20 caracteres.'))
```

- **Frontend (views/memoria_viva_templates.xml):**
```xml
<input type="text" name="dni_remitente" class="form-control" 
       required="required" 
       minlength="5"
       maxlength="20"
       placeholder="DNI, NIE, pasaporte..."/>
```

- **API (controllers/memoria_viva_website.py):**
```python
# Validar DNI (5-20 caracteres)
dni = data.get('dni_remitente', '').strip()
if not dni or len(dni) < 5 or len(dni) > 20:
    return {'success': False, 'error': 'El documento debe tener entre 5 y 20 caracteres'}
```

**Validación:**
| Caso | Resultado |
|------|-----------|
| ABC (3 chars) | ❌ Rechazado |
| 12345 (5 chars) | ✅ Aceptado |
| 12345678A (9 chars) | ✅ Aceptado |
| Cualquier texto 5-20 chars | ✅ Aceptado |

---

### 2.2 Cambio de Colores a Azul Corporativo

**Descripción:** Todos los botones y elementos verdes (`btn-success`, `bg-success`) cambiados a azul (`btn-primary`, `bg-primary`).

**Color utilizado:** `rgba(13, 71, 161, 0.75)` (azul corporativo)

**Elementos cambiados:**
- Botón "Compartir historia" en sidebar
- Botón "Enviar historia" en formulario
- Botón "Compartir historia" cuando no hay lugares
- Badges de categorías en tarjetas
- Badges de filtros activos

**Archivos modificados:**
- `views/memoria_viva_templates.xml`
- `__manifest__.py` (eliminados JS externos problemáticos)

---

### 2.3 Checkbox de Políticas Obligatorio

**Descripción:** Checkbox obligatorio para aceptar condiciones de la plataforma.

**Implementación:**
```xml
<div class="mb-3">
    <div class="form-check">
        <input class="form-check-input" type="checkbox" id="aceptaPoliticas" 
               name="acepta_politicas" required="required"/>
        <label class="form-check-label" for="aceptaPoliticas">
            Acepto las condiciones: Esta plataforma no se hace responsable 
            de los contenidos que puedan ser publicados por los usuarios.
        </label>
    </div>
</div>
```

**Nota:** Solo validación frontend (HTML5 required). No se guarda en BD.

---

### 2.4 Reorganización del Formulario

**Descripción:** Mover el formulario de envío debajo de la sección del concurso.

**Estructura anterior:**
```
Hero → Anuncio → Grid de Lugares → Formulario (al final)
```

**Estructura nueva:**
```
Hero → Anuncio → Sección Editable → Formulario → Grid de Lugares
```

**Cambios:**
- Formulario movido a `id="formulario-envio-section"`
- Eliminado formulario duplicado del final
- Actualizados los enlaces `#formulario-envio`

---

### 2.5 Imagen de Fondo en Hero

**Descripción:** Imagen de fondo fija en la sección hero con overlay azul.

**Implementación:**
```xml
<section class="shop-directory-header py-5 border-bottom position-relative" 
         style="padding: 120px 0 !important; 
                background: url('/memoria_viva/static/src/img/hero-bg.jpg') 
                           center/cover no-repeat fixed;">
    <div class="position-absolute top-0 start-0 w-100 h-100" 
         style="background: rgba(13, 71, 161, 0.75);"></div>
    <div class="container position-relative" style="z-index: 1;">
        <!-- contenido -->
    </div>
</section>
```

**Imagen:** `/home/odoo/ios_scan_1638839245_page-0001.jpg` copiada a `static/src/img/hero-bg.jpg`

---

### 2.6 Sección Editable con Website Builder

**Descripción:** Zona donde se pueden arrastrar bloques de contenido desde el editor de Odoo.

**Implementación:**
```xml
<section class="py-4">
    <div class="container oe_structure" 
         data-editor-message="Arrastra bloques de contenido aquí"/>
</section>
```

**Ubicación:** Entre el anuncio del concurso y el formulario.

---

### 2.7 Nuevas Categorías

**Descripción:** Reemplazo de las 14 categorías anteriores por 7 categorías planas.

**Nuevas Categorías:**
1. Historia
2. Costumbres
3. Edificios y casas
4. Gente
5. Fiestas
6. Actividades
7. Otros

**Mapeo de migración:**
| Categoría Vieja | Nueva Categoría |
|-----------------|-----------------|
| Playas | Actividades |
| Miradores | Edificios y casas |
| Edificios históricos | Historia |
| Instalaciones deportivas | Actividades |
| Parques | Edificios y casas |
| Teatros | Fiestas |
| Iglesias | Historia |
| Plazas | Edificios y casas |
| Gastronomía | Costumbres |
| Museos | Historia |
| Paseos | Actividades |
| Tiendas deportivas | Actividades |
| Centros comerciales | Edificios y casas |
| Bares/Vida nocturna | Fiestas |

**Resultado:** 10 historias migradas correctamente.

---

### 2.8 Anti-Spam Honeypot

**Descripción:** Campo invisible que detecta bots si se completa.

**Implementación:**
```xml
<div class="oh-no-honey" style="position: absolute; left: -9999px; opacity: 0;">
    <input type="text" name="website" tabindex="-1" autocomplete="off" value=""/>
</div>
```

**Validación:**
```python
if data.get('website'):  # Si el honeypot tiene valor = bot
    return {'success': False, 'error': 'Spam detectado'}
```

---

## 3. Problemas Encontrados y Soluciones

### Problema 1: Vistas Duplicadas
**Síntoma:** La página no se actualizaba correctamente.
**Causa:** Existían múltiples vistas con la misma key `memoria_viva.memoria_viva_list`.
**Solución:** Eliminar vistas duplicadas y dejar que Odoo recree la vista desde el archivo XML.

### Problema 2: JavaScript No Cargaba
**Síntoma:** Los logs `[MemoriaViva]` no aparecían en consola.
**Causa:** Los archivos JS externos requerían `web.public.widget` que no estaba disponible.
**Solución:** Mover todo el JavaScript inline al template XML y eliminar los archivos JS del manifest.

### Problema 3: Campo DNI No Se Enviaba
**Síntoma:** Error "DNI requerido" aunque se completaba el campo.
**Causa:** El JavaScript no incluía `dni_remitente` en el payload del fetch.
**Solución:** Agregar el campo al objeto payload en el JavaScript.

### Problema 4: Página en Blanco
**Síntoma:** `https://guanarteme.canariasconectada.es/memoria-viva` aparecía en blanco.
**Causa:** La vista en BD tenía el tag `<template>` envolviendo todo el HTML.
**Solución:** Eliminar la vista corrupta y recrearla correctamente.

### Problema 5: Validación DNI Muy Compleja
**Síntoma:** El DNI no pasaba la validación de formato.
**Causa:** Regex demasiado estricto que solo aceptaba formatos específicos.
**Solución:** Simplificar a solo validación de longitud (5-20 caracteres).

---

## 4. Validación y Testing

### Tests Backend (XML-RPC/Odoo Shell)

| Test | Descripción | Resultado |
|------|-------------|-----------|
| 1 | Conexión a Odoo | ✅ OK |
| 2 | Campo DNI existe | ✅ OK (Char, requerido) |
| 3 | Nuevas categorías | ✅ 7/7 creadas |
| 4 | Historias migradas | ✅ 10 historias |
| 5 | Categorías viejas desactivadas | ✅ 14 desactivadas |
| 6 | Validación DNI | ✅ 5-20 caracteres |

### Tests Frontend (HTTP/curl)

| Test | Descripción | Resultado |
|------|-------------|-----------|
| 7 | Página carga | ✅ HTTP 200 (<500ms) |
| 8 | Hero con imagen | ✅ hero-bg.jpg |
| 9 | Formulario ubicación | ✅ Después del concurso |
| 10 | Zona editable | ✅ oe_structure presente |
| 11 | Campo DNI | ✅ Con minlength/maxlength |
| 12 | Checkbox políticas | ✅ Obligatorio |
| 13 | Honeypot | ✅ Campo oculto |
| 14 | Categorías sidebar | ✅ 7 nuevas visibles |
| 15 | Imagen hero | ✅ HTTP 200 |
| 16 | HTML válido | ✅ Bien formado |

### Tests API Endpoint

| Test | Descripción | Resultado |
|------|-------------|-----------|
| 17 | Anti-spam honeypot | ✅ Rechaza bots |
| 18 | Validación DNI | ✅ Rechaza <5 chars |
| 19 | DNI válido | ✅ Acepta 5-20 chars |

---

## 5. Archivos Modificados

### Backend
- `models/memoria_viva_historia.py` - Campo DNI + validación longitud
- `controllers/memoria_viva_website.py` - Validación DNI API + import datetime
- `data/categorias_nuevas.xml` - Nuevas categorías (creado)
- `__manifest__.py` - Versión 19.0.2.0.0, eliminados JS externos

### Frontend
- `views/memoria_viva_templates.xml` - Formulario reestructurado, JavaScript inline
- `static/src/img/hero-bg.jpg` - Imagen de fondo (copiada)

### Scripts de Migración
- `scripts/migrar_categorias.py` - Script de migración de categorías (creado)

### Documentación
- `DOCUMENTACION_FILTROS.md` - Documentación sistema de filtros
- `VALIDACION_FASE1.md` - Resultados de validación
- `DOCUMENTACION_FASE1_COMPLETA.md` - Este documento

---

## 6. Backups

### Backups Creados (2026-04-08)
```
/home/odoo/backup/
├── memoria_viva_pre_cambios_20260408_062147.sql (468M)
└── memoria_viva_modulo_20260408_062202.tar.gz (102K)
```

### Limpieza Realizada
- Eliminados 25 backups antiguos (>30 días)
- Espacio liberado: ~15-20 GB

---

## 7. Próximos Pasos

### Fase 2 (Pendiente)
- Sistema de usuarios portal
- Creación automática de contacto por DNI
- Login para ver/editar envíos
- Asignación de contraseña

### Mejoras Futuras
- Recuperación de contraseña por email
- Dashboard de usuario
- Notificaciones de aprobación

---

## Anexos

### Comandos Útiles

```bash
# Actualizar módulo
cd /home/odoo/scripts && sudo ./update_module.sh memoria_viva

# Ver logs de Odoo
sudo journalctl -u odoo -f

# Backup manual
sudo -u postgres pg_dump canarias_conectada > backup.sql
```

### URLs Importantes
- Producción: https://guanarteme.canariasconectada.es/memoria-viva
- Backend: https://guanarteme.canariasconectada.es/web

---

**Documentación creada:** 2026-04-08  
**Autor:** Kimi Code CLI  
**Versión documento:** 1.0
