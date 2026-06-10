#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para migrar categorías viejas a nuevas categorías planas
Nuevas categorías: Historia, Costumbres, Edificios y casas, Gente, Fiestas, Actividades, Otros
"""

import xmlrpc.client
import sys

# Configuración
URL = 'http://localhost:8069'
DB = 'canarias_conectada'
USER = 'admin'
PASS = 'admin'  # Cambiar si es necesario

def main():
    print("🔄 Conectando a Odoo...")
    
    # Autenticación
    common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
    uid = common.authenticate(DB, USER, PASS, {})
    
    if not uid:
        print("❌ Error de autenticación")
        return False
    
    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
    
    # Mapeo de categorías viejas a nuevas
    # Nombres de categorías viejas -> Nombres de nuevas categorías
    mapeo_categorias = {
        # Playas -> Actividades (o Costumbres)
        'Playas': 'Actividades',
        # Miradores -> Edificios y casas / Historia
        'Miradores': 'Edificios y casas',
        # Edificios históricos -> Historia / Edificios y casas
        'Edificios históricos': 'Historia',
        # Instalaciones deportivas -> Actividades
        'Instalaciones deportivas': 'Actividades',
        # Parques -> Edificios y casas
        'Parques': 'Edificios y casas',
        # Teatros -> Edificios y casas / Fiestas
        'Teatros': 'Fiestas',
        # Iglesias -> Historia / Edificios y casas
        'Iglesias': 'Historia',
        # Plazas -> Edificios y casas
        'Plazas': 'Edificios y casas',
        # Gastronomía -> Costumbres
        'Gastronomía': 'Costumbres',
        # Museos -> Historia
        'Museos': 'Historia',
        # Paseos -> Actividades
        'Paseos': 'Actividades',
        # Tiendas deportivas -> Actividades
        'Tiendas deportivas': 'Actividades',
        # Centros comerciales -> Edificios y casas
        'Centros comerciales': 'Edificios y casas',
        # Bares/Vida nocturna -> Fiestas
        'Bares/Vida nocturna': 'Fiestas',
    }
    
    print("📋 Obteniendo categorías...")
    
    # Obtener todas las categorías
    categorias = models.execute_kw(DB, uid, PASS, 'lugares.interes.categoria', 'search_read', [
        [], ['id', 'name', 'active']
    ])
    
    # Obtener las nuevas categorías creadas
    cat_nuevas = models.execute_kw(DB, uid, PASS, 'lugares.interes.categoria', 'search_read', [
        [['tipo_id.name', '=', 'General']], ['id', 'name']
    ])
    
    cat_nuevas_dict = {c['name']: c['id'] for c in cat_nuevas}
    
    print(f"   Categorías nuevas encontradas: {list(cat_nuevas_dict.keys())}")
    
    # Procesar cada categoría vieja
    historias_actualizadas = 0
    
    for cat_vieja in categorias:
        nombre_viejo = cat_vieja['name']
        cat_vieja_id = cat_vieja['id']
        
        # Buscar el mapeo
        nombre_nuevo = mapeo_categorias.get(nombre_viejo)
        
        if nombre_nuevo and nombre_nuevo in cat_nuevas_dict:
            cat_nueva_id = cat_nuevas_dict[nombre_nuevo]
            
            # Buscar historias con esta categoría
            historias = models.execute_kw(DB, uid, PASS, 'lugares.interes.historia', 'search', [
                [['categoria_id', '=', cat_vieja_id]]
            ])
            
            if historias:
                print(f"   {nombre_viejo} -> {nombre_nuevo}: {len(historias)} historias")
                
                # Actualizar historias
                models.execute_kw(DB, uid, PASS, 'lugares.interes.historia', 'write', [
                    historias, {'categoria_id': cat_nueva_id}
                ])
                historias_actualizadas += len(historias)
            
            # Desactivar categoría vieja
            models.execute_kw(DB, uid, PASS, 'lugares.interes.categoria', 'write', [
                [cat_vieja_id], {'active': False}
            ])
    
    print(f"\n✅ Migración completada:")
    print(f"   Historias actualizadas: {historias_actualizadas}")
    print(f"   Categorías viejas desactivadas: {len(mapeo_categorias)}")
    
    return True

if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
