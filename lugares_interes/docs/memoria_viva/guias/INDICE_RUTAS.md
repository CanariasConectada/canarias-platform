# Índice de Rutas y Archivos

Este documento describe la ubicación de todos los archivos importantes del módulo Lugares de Interés.

## 📂 Estructura del Módulo

```
/home/odoo/addons/lugares_interes/
│
├── __manifest__.py                     # Configuración del módulo
├── __init__.py                         # Inicializador
│
├── 📁 models/                          # Modelos de datos
│   ├── __init__.py
│   ├── lugares_interes_historia.py        # Lugares/historias
│   ├── lugares_interes_comentario.py      # Sistema de comentarios
│   ├── lugares_interes_palabra_prohibida.py # Moderación
│   └── ... (otros modelos)
│
├── 📁 controllers/                     # Controladores web
│   ├── __init__.py
│   └── lugares_interes_website.py         # Endpoints API
│
├── 📁 views/                           # Vistas XML
│   ├── lugares_interes_templates.xml      # Templates frontend
│   ├── lugares_interes_comentario_views.xml # Vistas backend
│   └── ... (otras vistas)
│
├── 📁 static/                          # Assets estáticos
│   └── src/
│       ├── js/
│       │   └── lugares_interes_comments.js # JavaScript comentarios
│       └── css/
│           └── lugares_interes.scss       # Estilos
│
├── 📁 tests/                           # Tests unitarios
│   ├── __init__.py
│   ├── test_lugares_interes_models.py
│   ├── test_lugares_interes_comentarios.py
│   └── test_lugares_interes_website.py
│
├── 📁 scripts/                         # Scripts de utilidad
│   ├── tests/                          #   Tests ejecutables
│   │   ├── test_comentarios_frontend.py
│   │   ├── test_xmlrpc.py
│   │   └── test_orm.py
│   ├── utilidades/                     #   Scripts auxiliares
│   │   └── registrar_modelos.py
│   └── deployment/                     #   Deployment
│       └── apply_fixes.sh
│
├── 📁 docs/                            # Documentación
│   ├── README.md                       #   Índice principal
│   ├── guias/                          #   Guías de usuario
│   ├── api/                            #   Documentación API
│   ├── tests/                          #   Docs de tests
│   ├── backend/                        #   Docs de backend
│   ├── frontend/                       #   Docs de frontend
│   └── deployment/                     #   Docs de deployment
│
├── 📁 security/                        # Seguridad
│   ├── ir.model.access.csv
│   ├── lugares_interes_security.xml
│   └── lugares_interes_rules.xml
│
├── 📁 data/                            # Datos demo
│   └── lugares_interes_demo.xml
│
└── 📁 backup/                          # Backups (referencia)
    └── pre_mejoras_comentarios/        #   Backup de referencia
```

## 🌐 URLs Importantes

### Frontend (Website)
| URL | Descripción |
|-----|-------------|
| `/lugares-de-interes` | Listado de lugares |
| `/lugares-de-interes/<slug>` | Detalle de lugar |
| `/web/login` | Login de usuarios |

### API REST
| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/lugares-de-interes/comentario/listar` | GET | Listar comentarios |
| `/lugares-de-interes/comentario/enviar` | POST | Enviar comentario |
| `/lugares_interes/api/submit` | POST | Enviar lugar |
| `/lugares-de-interes/like/<id>` | POST | Dar like |

### Backend (Odoo)
| Ruta | Descripción |
|------|-------------|
| `/web#action=action_lugares_interes_historia` | Listado de lugares |
| `/web#action=action_lugares_interes_comentario` | Moderación de comentarios |
| `/web#action=action_lugares_interes_settings` | Configuración |

## 📋 Archivos de Configuración

| Archivo | Ubicación | Descripción |
|---------|-----------|-------------|
| `odoo.conf` | `/home/odoo/odoo.conf` | Configuración de Odoo |
| `__manifest__.py` | `/home/odoo/addons/lugares_interes/__manifest__.py` | Manifest del módulo |

## 💾 Backups

| Ubicación | Contenido |
|-----------|-----------|
| `/home/odoo/backup/pre_mejoras_comentarios/` | Backup completo previo a mejoras |
| `/home/odoo/logs/odoo.log` | Logs del sistema |

## 📝 Documentación Externa

| Archivo | Ubicación | Descripción |
|---------|-----------|-------------|
| `TEST_RESULTS.md` | `/home/odoo/TEST_RESULTS.md` | Resultados de tests |
| `MEMORIA_VIVA_RESUMEN_COMPLETO.md` | `/home/odoo/MEMORIA_VIVA_RESUMEN_COMPLETO.md` | Resumen completo |

---

**Nota**: Las rutas son relativas a `/home/odoo/` salvo que se indique lo contrario.
