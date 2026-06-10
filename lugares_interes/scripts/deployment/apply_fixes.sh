#!/bin/bash
# Script para aplicar correcciones de comentarios

echo "=============================================="
echo "Aplicando correcciones de comentarios"
echo "=============================================="

# Cambiar al usuario odoo
su - odoo << 'ODOOEOF'

cd /home/odoo

echo ""
echo "1. Actualizando módulo memoria_viva..."
./odoo/odoo-bin -u memoria_viva -d canarias_conectada --stop-after-init --no-http -c odoo.conf 2>&1 | tail -20

echo ""
echo "2. Verificando cambios..."
psql canarias_conectada -c "SELECT column_name FROM information_schema.columns WHERE table_name='memoria_viva_comentario' AND column_name LIKE '%imagen%';"

echo ""
echo "=============================================="
echo "Correcciones aplicadas"
echo "=============================================="

ODOOEOF

echo ""
echo "3. Reiniciando servidor Odoo..."
pkill -f 'odoo-bin' 2>/dev/null
sleep 3
su - odoo -c "cd /home/odoo && nohup ./odoo/odoo-bin -c odoo.conf > /home/odoo/logs/odoo.log 2>&1 &"

echo ""
echo "Esperando 15 segundos para que el servidor inicie..."
sleep 15

echo ""
echo "4. Verificando estado..."
curl -s -o /dev/null -w "%{http_code}" "https://guanarteme.canariasconectada.es/memoria-viva" 2>&1

echo ""
echo "=============================================="
echo "Proceso completado"
echo "=============================================="
