# Guía de Backup - Memoria Viva

## 📁 Backup Automático Creado

**Ubicación**: `/home/odoo/backup/pre_mejoras_comentarios/`

**Fecha**: 6 de abril de 2026

---

## Archivos de Backup

### 1. database_backup.sql (461 MB)
Backup completo de PostgreSQL.

**Contenido**:
- Esquema completo de la base de datos
- Datos de todos los modelos
- Configuraciones
- Usuarios y permisos
- Comentarios, lugares, likes

### 2. memoria_viva_module.tar.gz (87 KB)
Código fuente del módulo.

**Contenido**:
- Todos los archivos Python
- Vistas XML
- JavaScript y CSS
- Tests y scripts

### 3. README.md
Instrucciones de restauración.

---

## Cómo Crear Nuevo Backup

### Backup Completo

```bash
#!/bin/bash

# Crear directorio de backup
BACKUP_DIR="/home/odoo/backup/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# Backup de base de datos
su - odoo -c "pg_dump canarias_conectada > $BACKUP_DIR/database_backup.sql"

# Backup del módulo
tar -czf $BACKUP_DIR/memoria_viva_module.tar.gz \
  -C /home/odoo/addons memoria_viva

# Backup de configuración
cp /home/odoo/odoo.conf $BACKUP_DIR/

# Backup de logs (opcional)
cp /home/odoo/logs/odoo.log $BACKUP_DIR/ 2>/dev/null || true

echo "Backup creado en: $BACKUP_DIR"
ls -lh $BACKUP_DIR
```

### Backup Solo de Comentarios

```bash
# Exportar solo tabla de comentarios
su - odoo -c "pg_dump canarias_conectada \
  --table=memoria_viva_comentario \
  --table=memoria_viva_palabra_prohibida \
  > /home/odoo/backup/comentarios_backup.sql"
```

---

## Cómo Restaurar

### Restauración Completa

⚠️ **ADVERTENCIA**: Esto sobrescribirá todos los datos actuales.

```bash
# 1. Detener Odoo
pkill -f 'odoo-bin'

# 2. Restaurar base de datos
su - odoo
dropdb canarias_conectada 2>/dev/null || true
createdb canarias_conectada
psql canarias_conectada < /home/odoo/backup/pre_mejoras_comentarios/database_backup.sql

# 3. Restaurar módulo
cd /home/odoo/addons
rm -rf memoria_viva
tar -xzf /home/odoo/backup/pre_mejoras_comentarios/memoria_viva_module.tar.gz

# 4. Reiniciar Odoo
nohup ./odoo/odoo-bin -c odoo.conf > logs/odoo.log 2>&1 &
```

### Restauración Parcial (Solo Comentarios)

```bash
# Solo restaurar comentarios (sin borrar otros datos)
su - odoo -c "psql canarias_conectada < /home/odoo/backup/comentarios_backup.sql"
```

---

## Verificación Post-Restauración

```bash
# Verificar que el módulo está instalado
su - odoo -c "psql canarias_conectada -c \"SELECT name, state FROM ir_module_module WHERE name='memoria_viva';\""

# Verificar comentarios
su - odoo -c "psql canarias_conectada -c \"SELECT COUNT(*) FROM memoria_viva_comentario;\""

# Verificar palabras prohibidas
su - odoo -c "psql canarias_conectada -c \"SELECT COUNT(*) FROM memoria_viva_palabra_prohibida;\""
```

---

## Estrategia de Backups

### Recomendación

| Tipo | Frecuencia | Retención |
|------|------------|-----------|
| Diario | Automático | 7 días |
| Semanal | Manual | 4 semanas |
| Mensual | Manual | 12 meses |
| Pre-cambios | Manual | Permanente |

### Script de Backup Diario

```bash
#!/bin/bash
# /home/odoo/scripts/backup_diario.sh

BACKUP_DIR="/home/odoo/backup/daily"
DATE=$(date +%Y%m%d)

mkdir -p $BACKUP_DIR

# Backup
su - odoo -c "pg_dump canarias_conectada | gzip > $BACKUP_DIR/${DATE}_database.sql.gz"

# Limpiar backups antiguos (más de 7 días)
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete

echo "Backup diario completado: $DATE"
```

---

## Troubleshooting

### Error: "database not found"
```bash
# Verificar que la base existe
su - odoo -c "psql -l | grep canarias_conectada"
```

### Error: "permission denied"
```bash
# Asegurar permisos correctos
chown -R odoo:odoo /home/odoo/backup
```

### Backup corrupto
```bash
# Verificar integridad
gunzip -t backup.sql.gz
```

---

## Referencias

- Backup actual: `/home/odoo/backup/pre_mejoras_comentarios/`
- Logs: `/home/odoo/logs/odoo.log`
- Documentación completa: `/home/odoo/addons/memoria_viva/docs/`
