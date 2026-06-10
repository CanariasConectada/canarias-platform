# Índice de Rutas y Archivos

Este documento describe la ubicación de todos los archivos importantes del módulo Memoria Viva.

## 📂 Estructura del Módulo

```
/home/odoo/addons/memoria_viva/
│
├── __manifest__.py                     # Configuración del módulo
├── __init__.py                         # Inicializador
│
├── 📁 models/                          # Modelos de datos
│   ├── __init__.py
│   ├── memoria_viva_historia.py        # Lugares/historias
│   ├── memoria_viva_comentario.py      # Sistema de comentarios
│   ├── memoria_viva_palabra_prohibida.py # Moderación
│   └── ... (otros modelos)
│
├── 📁 controllers/                     # Controladores web
│   ├── __init__.py
│   └── memoria_viva_website.py         # Endpoints API
│
├── 📁 views/                           # Vistas XML
│   ├── memoria_viva_templates.xml      # Templates frontend
│   ├── memoria_viva_comentario_views.xml # Vistas backend
│   └── ... (otras vistas)
│
├── 📁 static/                          # Assets estáticos
│   └── src/
│       ├── js/
│       │   └── memoria_viva_comments.js # JavaScript comentarios
│       └── css/
│           └── memoria_viva.scss       # Estilos
│
├── 📁 tests/                           # Tests unitarios
│   ├── __init__.py
│   ├── test_memoria_viva_models.py
│   ├── test_memoria_viva_comentarios.py
│   └── test_memoria_viva_website.py
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
│   ├── memoria_viva_security.xml
│   └── memoria_viva_rules.xml
│
├── 📁 data/                            # Datos demo
│   └── memoria_viva_demo.xml
│
└── 📁 backup/                          # Backups (referencia)
    └── pre_mejoras_comentarios/        #   Backup de referencia
```

## 🌐 URLs Importantes

### Frontend (Website)
| URL | Descripción |
|-----|-------------|
| `/memoria-viva` | Listado de lugares |
| `/memoria-viva/<slug>` | Detalle de lugar |
| `/web/login` | Login de usuarios |

### API REST
| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/memoria-viva/comentario/listar` | GET | Listar comentarios |
| `/memoria-viva/comentario/enviar` | POST | Enviar comentario |
| `/memoria_viva/api/submit` | POST | Enviar lugar |
| `/memoria-viva/like/<id>` | POST | Dar like |

### Backend (Odoo)
| Ruta | Descripción |
|------|-------------|
| `/web#action=action_memoria_viva_historia` | Listado de lugares |
| `/web#action=action_memoria_viva_comentario` | Moderación de comentarios |
| `/web#action=action_memoria_viva_settings` | Configuración |

## 📋 Archivos de Configuración

| Archivo | Ubicación | Descripción |
|---------|-----------|-------------|
| `odoo.conf` | `/home/odoo/odoo.conf` | Configuración de Odoo |
| `__manifest__.py` | `/home/odoo/addons/memoria_viva/__manifest__.py` | Manifest del módulo |

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
