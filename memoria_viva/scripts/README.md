# Scripts de Memoria Viva

Este directorio contiene todos los scripts de utilidad para el módulo **Memoria Viva**.

## 📁 Estructura

```
scripts/
├── tests/                    # Scripts de testing
│   ├── test_comentarios_frontend.py    # Tests completos de frontend (18 tests)
│   ├── test_orm.py                     # Tests ORM directo
│   └── test_xmlrpc.py                  # Tests vía XML-RPC
├── utilidades/               # Scripts de utilidad
│   └── registrar_modelos.py            # Registro manual de modelos en ir_model
└── deployment/               # Scripts de deployment
    └── apply_fixes.sh                  # Aplicar correcciones y reiniciar
```

## 🧪 Tests

### Ejecutar Tests Frontend Completos
```bash
cd /home/odoo/addons/memoria_viva
python3 scripts/tests/test_comentarios_frontend.py
```

### Ejecutar Tests ORM
```bash
cd /home/odoo/addons/memoria_viva
python3 scripts/tests/test_orm.py
```

### Ejecutar Tests XML-RPC
```bash
cd /home/odoo/addons/memoria_viva
python3 scripts/tests/test_xmlrpc.py
```

## 🛠️ Utilidades

### Registrar Modelos Manualmente
```bash
python3 scripts/utilidades/registrar_modelos.py
```

## 🚀 Deployment

### Aplicar Correcciones y Reiniciar
```bash
sudo bash scripts/deployment/apply_fixes.sh
```

## 📊 Estado

- **Tests**: 18/18 pasando (100%)
- **Última actualización**: Abril 2026
