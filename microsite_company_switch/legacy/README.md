# Archivos Legacy - microsite_company_switch

## ¿Qué es esta carpeta?

Contiene archivos antiguos que ya NO se utilizan pero se mantienen por referencia histórica.

## Lista de Archivos

| Archivo | Descripción | Fecha Desactivación |
|---------|-------------|---------------------|
| `company_cookie.py.disabled` | Controller para manejar cookie de compañía | 2026-03-25 |
| `ir_http.py.disabled` | Versión anterior del manejo de HTTP | 2026-03-25 |
| `ir_rule.py.disabled` | Código Python para reglas de seguridad | 2026-03-25 |
| `res_partner.py.disabled` | Create() personalizado para partners | 2026-03-25 |
| `switcher_fix.py.disabled` | Fix vía controller para switcher | 2026-03-25 |

## ¿Por qué se desactivaron?

Estos archivos fueron reemplazados por implementaciones más simples y efectivas:

1. **Nueva implementación en `models/ir_http.py`**: Más limpia y funcional
2. **Reglas en XML**: Mejor manejo vía `security/security_rules.xml`
3. **Login simplificado**: Sin `/web/set_company`, directo a `/odoo`

## ¿Se pueden eliminar?

**Sí**, después de validar que el sistema funciona estable por al menos 1 semana.

Backups disponibles en:
- `/home/odoo/backup/PRE_LIMPIEZA_FASE1_*`
- `/home/odoo/backup/EXTRA_SEGURIDAD_FASE1_*`

## Estado Actual del Sistema (2026-03-25)

✅ Company switcher funciona para usuarios normales  
✅ Company switcher funciona para admins  
✅ Login directo sin errores  
✅ Aislamiento de contactos por compañía activo  
