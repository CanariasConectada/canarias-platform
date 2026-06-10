# Lugares de Interés - Módulo Odoo 19

[![Odoo Version](https://img.shields.io/badge/Odoo-19.0-blue.svg)](https://odoo.com)
[![Status](https://img.shields.io/badge/Estado-Producción-green.svg)]()

Módulo para gestionar historias, lugares, eventos y sistema de comentarios con moderación.

---

## 📋 Características

- **Galería de Lugares**: Gestión de lugares con imágenes, coordenadas GPS y categorización
- **Eventos**: Calendario de eventos asociados a lugares
- **Sistema de Anuncios**: Publicidad gestionable por posición
- **Sistema de Comentarios** (NUEVO): 
  - Comentarios con moderación
  - Respuestas anidadas (1 nivel)
  - Filtro de palabras prohibidas
  - Panel de moderación en backend

---

## 📁 Estructura del Proyecto

```
lugares_interes/
├── models/              # Modelos de datos
├── controllers/         # Controladores web y API
├── views/               # Vistas XML (backend y frontend)
├── security/            # Permisos y grupos
├── static/              # CSS, JS, imágenes
├── tests/               # Tests automatizados
├── scripts/             # Scripts de utilidad
└── docs/                # Documentación
```

---

## 📚 Documentación

### Documentación Principal
- [📖 Implementación Sistema de Comentarios](docs/IMPLEMENTACION_SISTEMA_COMENTARIOS.md) - Guía completa del sistema de comentarios
- [🔧 API Endpoints](docs/lugares_interes/api/ENDPOINTS.md) - Documentación de API REST
- [🏗️ Modelos](docs/lugares_interes/backend/MODELOS.md) - Documentación de modelos
- [🎨 Frontend](docs/lugares_interes/frontend/ESTILOS.md) - Guía de estilos CSS

### Scripts y Utilidades
- [🧪 Tests](scripts/tests/) - Scripts de testing
- [🚀 Deployment](scripts/deployment/) - Scripts de deployment

---

## 🚀 Instalación

### Requisitos
- Odoo 19.0+
- Módulos base: `base`, `website`

### Pasos

1. Clonar/copiar el módulo a `/home/odoo/addons/`
2. Actualizar lista de aplicaciones en Odoo
3. Buscar "Lugares de Interés" en Apps
4. Instalar

---

## 🔄 Actualización

Después de actualizar archivos:

```bash
# Desde interfaz web
Apps → Lugares de Interés → Actualizar (↻)

# O desde consola
sudo systemctl restart odoo
```

---

## 🧪 Tests

```bash
cd /home/odoo/addons/lugares_interes

# Tests de frontend/API
python3 scripts/tests/test_comentarios_frontend.py

# Tests de modelos
python3 scripts/tests/test_orm.py
```

**Estado:** 18/18 tests pasando ✅

---

## 🛡️ Seguridad

### Grupos Disponibles
- **Aprobador**: Acceso completo al módulo
- **Moderador de Comentarios**: Solo moderación de comentarios
- **Anuncios / Administrador**: Gestión de anuncios
- **Anuncios / Editor**: Crear/editar anuncios

### Menú de Moderación
```
Lugares de Interés
├── Contenido
├── Clasificación
├── 🛡️ Moderación ← Visible para todos
│   ├── Comentarios
│   └── Palabras Prohibidas
└── Configuración
```

---

## 📞 Soporte

Para reportar problemas o solicitar mejoras:
- Email: miguelangel1074.gc@gmail.com
- Web: https://disoft.canariasconectada.es

---

## 📄 Licencia

LGPL-3

---

**Versión:** 19.0.1.3.0  
**Última actualización:** Abril 2026  
**Autor:** DISOFT
