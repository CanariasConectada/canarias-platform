# Índice Maestro de Documentación

## 📚 Estructura Completa de Documentación

```
/home/odoo/addons/memoria_viva/
│
├── 📖 INDICE_DOCUMENTACION.md          # Este archivo
├── 📘 README.md                          # Descripción general del módulo
│
├── 📁 docs/                              # DOCUMENTACIÓN
│   ├── README.md                         #   Índice de documentación
│   ├── guias/                            #   Guías de usuario
│   │   ├── INDICE_RUTAS.md               #     Ubicación de todos los archivos
│   │   ├── USUARIO.md                    #     Guía para usuarios finales
│   │   ├── DESARROLLADOR.md              #     Guía para desarrolladores
│   │   ├── MODERACION.md                 #     Guía de moderación
│   │   └── INSTALACION.md                #     Guía de instalación
│   │
│   ├── api/                              #   Documentación de API
│   │   ├── ENDPOINTS.md                  #     Referencia de endpoints
│   │   └── EJEMPLOS.md                   #     Ejemplos de uso
│   │
│   ├── tests/                            #   Documentación de tests
│   │   ├── INDICE.md                     #     Índice de tests
│   │   ├── RESULTADOS.md                 #     Resultados ejecutados
│   │   └── COBERTURA.md                  #     Cobertura de tests
│   │
│   ├── backend/                          #   Documentación del backend
│   │   ├── MODELOS.md                    #     Modelos de datos
│   │   ├── VISTAS.md                     #     Vistas del backend
│   │   └── PERMISOS.md                   #     Matriz de permisos
│   │
│   ├── frontend/                         #   Documentación del frontend
│   │   ├── COMPONENTES.md                #     Componentes JavaScript
│   │   ├── ESTILOS.md                    #     Guía de estilos CSS
│   │   └── TEMPLATES.md                  #     Templates QWeb
│   │
│   └── deployment/                       #   Documentación de deployment
│       ├── BACKUP.md                     #     Procedimientos de backup
│       ├── RESTAURACION.md               #     Procedimientos de restauración
│       └── TROUBLESHOOTING.md            #     Solución de problemas
│
├── 📁 scripts/                           # SCRIPTS
│   ├── README.md                         #   Índice de scripts
│   ├── tests/                            #   Scripts de testing
│   │   ├── test_comentarios_frontend.py  #     Tests completos (18 tests)
│   │   ├── test_xmlrpc.py                #     Tests XML-RPC
│   │   └── test_orm.py                   #     Tests ORM directo
│   │
│   ├── utilidades/                       #   Scripts auxiliares
│   │   └── registrar_modelos.py          #     Registro manual de modelos
│   │
│   └── deployment/                       #   Scripts de deployment
│       └── apply_fixes.sh                #     Aplicar correcciones
│
└── 📁 tests/                             # TESTS UNITARIOS (Odoo)
    ├── __init__.py
    ├── test_memoria_viva_models.py       #   Tests de modelos
    ├── test_memoria_viva_comentarios.py  #   Tests de comentarios
    └── test_memoria_viva_website.py      #   Tests de website
```

---

## 🗺️ Mapa de Rutas Absolutas

### Código Fuente del Módulo

| Componente | Ruta Absoluta |
|------------|---------------|
| Manifest | `/home/odoo/addons/memoria_viva/__manifest__.py` |
| Modelos | `/home/odoo/addons/memoria_viva/models/` |
| Controladores | `/home/odoo/addons/memoria_viva/controllers/` |
| Vistas XML | `/home/odoo/addons/memoria_viva/views/` |
| JavaScript | `/home/odoo/addons/memoria_viva/static/src/js/` |
| CSS | `/home/odoo/addons/memoria_viva/static/src/css/` |

### Documentación

| Documento | Ruta Absoluta |
|-----------|---------------|
| Índice principal | `/home/odoo/addons/memoria_viva/docs/README.md` |
| Índice de rutas | `/home/odoo/addons/memoria_viva/docs/guias/INDICE_RUTAS.md` |
| API Endpoints | `/home/odoo/addons/memoria_viva/docs/api/ENDPOINTS.md` |
| Tests | `/home/odoo/addons/memoria_viva/docs/tests/INDICE.md` |
| Modelos | `/home/odoo/addons/memoria_viva/docs/backend/MODELOS.md` |
| Estilos | `/home/odoo/addons/memoria_viva/docs/frontend/ESTILOS.md` |
| Backup | `/home/odoo/addons/memoria_viva/docs/deployment/BACKUP.md` |

### Scripts

| Script | Ruta Absoluta |
|--------|---------------|
| Tests frontend | `/home/odoo/addons/memoria_viva/scripts/tests/test_comentarios_frontend.py` |
| Tests XML-RPC | `/home/odoo/addons/memoria_viva/scripts/tests/test_xmlrpc.py` |
| Tests ORM | `/home/odoo/addons/memoria_viva/scripts/tests/test_orm.py` |
| Aplicar fixes | `/home/odoo/addons/memoria_viva/scripts/deployment/apply_fixes.sh` |

### Tests Unitarios

| Test | Ruta Absoluta |
|------|---------------|
| Models | `/home/odoo/addons/memoria_viva/tests/test_memoria_viva_models.py` |
| Comentarios | `/home/odoo/addons/memoria_viva/tests/test_memoria_viva_comentarios.py` |
| Website | `/home/odoo/addons/memoria_viva/tests/test_memoria_viva_website.py` |

### Backups

| Backup | Ruta Absoluta |
|--------|---------------|
| Backup completo | `/home/odoo/backup/pre_mejoras_comentarios/` |
| Database SQL | `/home/odoo/backup/pre_mejoras_comentarios/database_backup.sql` |
| Módulo tar.gz | `/home/odoo/backup/pre_mejoras_comentarios/memoria_viva_module.tar.gz` |

---

## 🔗 URLs del Sistema

### Frontend (Website)
- Listado: `https://guanarteme.canariasconectada.es/memoria-viva`
- Detalle: `https://guanarteme.canariasconectada.es/memoria-viva/<slug>`
- Login: `https://guanarteme.canariasconectada.es/web/login`

### API REST
- Listar comentarios: `GET /memoria-viva/comentario/listar`
- Enviar comentario: `POST /memoria-viva/comentario/enviar`
- Dar like: `POST /memoria-viva/like/<id>`

### Backend (Odoo Admin)
- Lugares: `/web#action=action_memoria_viva_historia`
- Comentarios: `/web#action=action_memoria_viva_comentario`
- Configuración: `/web#action=action_memoria_viva_settings`

---

## 📋 Checklist de Documentación

### Guías de Usuario ✅
- [x] Índice de rutas
- [ ] Guía de usuario final
- [ ] Guía de desarrollador
- [ ] Guía de moderación
- [ ] Guía de instalación

### API ✅
- [x] Referencia de endpoints
- [ ] Ejemplos de uso

### Tests ✅
- [x] Índice de tests
- [x] Resultados de tests
- [ ] Cobertura detallada

### Backend ✅
- [x] Modelos de datos
- [ ] Vistas del backend
- [ ] Matriz de permisos

### Frontend ✅
- [ ] Componentes JavaScript
- [x] Guía de estilos
- [ ] Templates QWeb

### Deployment ✅
- [x] Procedimientos de backup
- [ ] Procedimientos de restauración
- [ ] Solución de problemas

---

## 🚀 Inicio Rápido

### Para Encontrar Cualquier Archivo

1. **Consultar índice de rutas**: `docs/guias/INDICE_RUTAS.md`
2. **Buscar en este índice**: `INDICE_DOCUMENTACION.md`
3. **Scripts disponibles**: `scripts/README.md`

### Para Ejecutar Tests

```bash
# Tests completos
cd /home/odoo
python3 addons/memoria_viva/scripts/tests/test_comentarios_frontend.py

# Tests unitarios de Odoo
./odoo-bin -i memoria_viva -d canarias_conectada --test-enable --stop-after-init
```

### Para Crear Backup

```bash
bash /home/odoo/addons/memoria_viva/scripts/deployment/apply_fixes.sh
```

---

**Última actualización**: 6 de abril de 2026

**Mantenido por**: Equipo de desarrollo Memoria Viva
