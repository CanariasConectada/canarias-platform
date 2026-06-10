# Changelog - Memoria Viva

Todas las modificaciones notables a este proyecto serán documentadas en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

## [1.5.0] - 2026-04-09

### Added
- Grid mejorado con stats visibles: likes ❤️, comentarios 💬, valoración ⭐
- Tarjetas completamente clickeables (foto, título, botón → detalle)
- Sidebar con filtros funcionales: Tipo, Categoría, Décadas (select), Ordenar
- Select de décadas: 1840-2020 (step 10 años)
- Opciones de ordenamiento: Mejor valorados, Más reacciones, Más comentados, Más antiguos, Más recientes
- Botón "Quitar filtros" (papelera 🗑️) debajo del sidebar
- Like público AJAX: sin login, sin recargar, cookie-based
- Botón like en esquina superior derecha de cada card
- JavaScript para manejar likes con fetch API
- Filtro por década en controlador (`decada_filter`)

### Changed
- Orden por defecto: `rating_avg desc` (mejor valorados primero)
- Badge de tipo removido de las tarjetas (solo categoría)
- Textos de filtros más concisos ("Todos" en lugar de "Todos los tipos")

### Removed
- Badge de tipo en cards del grid

## [1.4.0] - 2026-04-09

### Added
- Card de usuario logueado en sección "Tus Datos" con nombre, email y foto
- Auto-login después de registro exitoso (7 segundos de espera)
- Mensaje de éxito con cuenta regresiva para usuarios logueados (5 segundos)
- Campo `user_id` y `partner_id` ocultos para usuarios autenticados

### Changed
- Dirección ahora es campo obligatorio (*)
- Descripción corta ahora es campo obligatorio (*)
- Refactor de mensajes de éxito: unificado comportamiento login/registro/logueado

### Fixed
- Validación de campos obligatorios en JavaScript (dirección, descripción)

## [1.3.0] - 2026-04-09

### Added
- Tabs Bootstrap en "Tus Datos": "Crear cuenta" / "Iniciar sesión"
- Campos de registro separados: nombre, DNI, email, teléfono, contraseña, confirmar
- Card de errores estilizada (debajo del botón, sin alerts)
- Especificaciones de imagen en el formulario (400x400 a 1200x1200, max 500KB)
- Validación de tamaño de imagen en JavaScript (500KB máximo)
- Validación de contraseñas coincidentes

### Changed
- Campos de usuario movidos de "Datos de la Fotografía" a tab "Crear cuenta"
- Eliminados campos duplicados: publicador_nombre, publicador_email, publicador_telefono del formulario principal

### Removed
- Checkbox de políticas duplicado

## [1.2.0] - 2026-04-09

### Added
- Formulario dividido en dos secciones: "Tus Datos" y "Datos de la Fotografía"
- JavaScript API completo con FileReader para imagen base64
- Campos opcionales enviados: tipo_id, categoria_id, coordenadas, descripcion_larga
- Modo auth dinámico (login/registro)

### Changed
- Texto del título: "Enviar fotografía" (antes "Compartir un lugar histórico")
- Campos obligatorios marcados con asterisco (*)

## [1.1.0] - 2026-04-09

### Added
- Sección editable con `oe_structure` para Website Builder
- Mensaje por defecto: "Arrastra bloques aquí para personalizar"

## [1.0.0] - 2026-04-09

### Added
- Hero section con imagen hero-cine-astoria.jpg
- Overlay azul al 55% (rgba(13, 71, 161, 0.55))
- Contador de "X fotos" (cambiado de "lugares")
- Banner configurable conectado a Ajustes

---

## Notas de Versiones

- **v1.4.0**: Mejoras de UX post-registro y campos obligatorios adicionales
- **v1.3.0**: Sistema de tabs de autenticación completo
- **v1.2.0**: Estructura del formulario base
- **v1.1.0**: Integración Website Builder
- **v1.0.0**: Personalización visual inicial

## Git Tags

```bash
# Ver tags existentes
git tag -l

# Ver historial con tags
git log --oneline --decorate --tags
```

## Comandos Útiles

```bash
# Actualizar módulo
./odoo-bin -c odoo.conf -d canarias_conectada -u memoria_viva --stop-after-init

# Ver logs
tail -f logs/odoo.log | grep memoria_viva
```
