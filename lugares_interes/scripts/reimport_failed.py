#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reimporta los 3 registros que fallaron en la importación principal.
"""
import csv
import os
import sys
import base64
import zipfile
import tempfile
import xmlrpc.client
from PIL import Image
import io

ODOO_URL = 'http://localhost:8069'
DB = 'canarias_conectada'
ADMIN_USER = 'miguelangel1074.gc@gmail.com'
ADMIN_PASS = 'gtMnLgDxbw9NO71C'

CSV_PATH = '/home/odoo/lugares_de_interes_importacion/lugares-20260505-V1.0.csv'
ZIP_PATH = '/home/odoo/lugares_de_interes_importacion/ANTIGUAS.zip'

BARRIO_TO_WEBSITE = {
    'Guanarteme': 229,
    'Tamaraceite': 231,
    'Lomo Los Frailes': 230,
}
DEFAULT_WEBSITE_ID = 228

FAILED_IDS = [54, 107, 52]


def connect():
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(DB, ADMIN_USER, ADMIN_PASS, {})
    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    return uid, models


def get_or_create_tag(models, uid, model, name):
    tag_id = models.execute_kw(DB, uid, ADMIN_PASS, model, 'search', [[('name', '=', name)]], {'limit': 1})
    if tag_id:
        return tag_id[0]
    return models.execute_kw(DB, uid, ADMIN_PASS, model, 'create', [{'name': name}])


def get_or_create_category(models, uid, model, name, parent_id=None):
    domain = [('name', '=', name)]
    if parent_id and model == 'lugares.interes.categoria':
        domain.append(('tipo_id', '=', parent_id))
    elif parent_id and model == 'lugares.interes.subcategoria':
        domain.append(('categoria_id', '=', parent_id))
    rec_id = models.execute_kw(DB, uid, ADMIN_PASS, model, 'search', [domain], {'limit': 1})
    if rec_id:
        return rec_id[0]
    vals = {'name': name}
    if parent_id and model == 'lugares.interes.categoria':
        vals['tipo_id'] = parent_id
    elif parent_id and model == 'lugares.interes.subcategoria':
        vals['categoria_id'] = parent_id
    return models.execute_kw(DB, uid, ADMIN_PASS, model, 'create', [vals])


def process_image(path, max_kb=1900):
    """Comprimir imagen si excede tamaño, convertir webp a jpg"""
    with open(path, 'rb') as f:
        data = f.read()
    
    # Si es webp, convertir a jpg
    if path.lower().endswith('.webp'):
        img = Image.open(io.BytesIO(data))
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        output = io.BytesIO()
        img.save(output, 'JPEG', quality=90, optimize=True)
        data = output.getvalue()
        print(f"  Converted WEBP to JPEG: {len(data)/1024:.0f}KB")
    
    # Comprimir si excede tamaño
    if len(data) > max_kb * 1024:
        img = Image.open(io.BytesIO(data))
        quality = 85
        while len(data) > max_kb * 1024 and quality > 50:
            output = io.BytesIO()
            img.save(output, 'JPEG', quality=quality, optimize=True)
            data = output.getvalue()
            quality -= 5
        print(f"  Compressed to {len(data)/1024:.0f}KB (quality={quality})")
    
    return base64.b64encode(data).decode('utf-8')


def main():
    print("[+] Conectando a Odoo...")
    uid, models = connect()
    
    extract_dir = tempfile.mkdtemp(prefix='lugares_interes_fix_')
    with zipfile.ZipFile(ZIP_PATH, 'r') as z:
        z.extractall(extract_dir)
    
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        rows = {int(r['id']): r for r in csv.DictReader(f)}
    
    for lugar_id in FAILED_IDS:
        row = rows.get(lugar_id)
        if not row:
            print(f"[!] ID {lugar_id} no encontrado en CSV")
            continue
        
        name = row['nombre']
        print(f"\n[+] Procesando ID {lugar_id}: {name}")
        
        # Buscar carpeta de imágenes
        folder = os.path.join(extract_dir, 'ANTIGUAS', str(lugar_id), '_antiguas')
        if not os.path.isdir(folder):
            print(f"  [!] Carpeta no encontrada: {folder}")
            continue
        
        files = sorted([f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
        files = [f for f in files if 'streetview' not in f.lower()]
        files = [os.path.join(folder, f) for f in sorted(files)]
        
        if not files:
            print(f"  [!] No hay imágenes")
            continue
        
        # Procesar imagen destacada
        try:
            image_main = process_image(files[0])
            print(f"  Destacada: {os.path.basename(files[0])} -> OK")
        except Exception as e:
            print(f"  ERROR destacada: {e}")
            image_main = None
        
        # Procesar imágenes adicionales
        image_ids_vals = []
        for seq, path in enumerate(files[1:], 1):
            try:
                img_b64 = process_image(path)
                image_ids_vals.append((0, 0, {
                    'sequence': seq,
                    'name': os.path.basename(path),
                    'image': img_b64,
                }))
                print(f"  Adicional {seq}: {os.path.basename(path)} -> OK")
            except Exception as e:
                print(f"  ERROR adicional {seq}: {e}")
        
        # Preparar datos del registro
        barrio = row['barrio']
        website_id = BARRIO_TO_WEBSITE.get(barrio, DEFAULT_WEBSITE_ID)
        
        lat, lng = None, None
        if row['coordenadas'] and '|' in row['coordenadas']:
            try:
                lat, lng = map(float, row['coordenadas'].split('|'))
            except ValueError:
                pass
        
        tipo_id = get_or_create_category(models, uid, 'lugares.interes.tipo', row['tipo'].strip()) if row['tipo'].strip() else None
        categoria_id = get_or_create_category(models, uid, 'lugares.interes.categoria', row['categoria'].strip(), tipo_id) if row['categoria'].strip() else None
        subcategoria_id = get_or_create_category(models, uid, 'lugares.interes.subcategoria', row['subcategoria'].strip(), categoria_id) if row['subcategoria'].strip() else None
        
        publico_ids = []
        for tag in row['publico_objetivo'].split(','):
            tag = tag.strip()
            if tag:
                publico_ids.append(get_or_create_tag(models, uid, 'lugares.interes.publico.objetivo', tag))
        
        momento_ids = []
        for tag in row['momento_dia'].split(','):
            tag = tag.strip()
            if tag:
                momento_ids.append(get_or_create_tag(models, uid, 'lugares.interes.momento.dia', tag))
        
        ambiente_ids = []
        for tag in row['ambiente'].split(','):
            tag = tag.strip()
            if tag:
                ambiente_ids.append(get_or_create_tag(models, uid, 'lugares.interes.ambiente', tag))
        
        experiencia_ids = []
        for tag in row['experiencias'].split(','):
            tag = tag.strip()
            if tag:
                experiencia_ids.append(get_or_create_tag(models, uid, 'lugares.interes.experiencia', tag))
        
        vals = {
            'name': name,
            'slug': row['slug'],
            'barrio': barrio,
            'ciudad': row['ciudad'],
            'direccion': row['direccion'],
            'description': row['descripcion_corta'],
            'descripcion_larga': row['descripcion_larga'],
            'horario': row['horario'],
            'tags_busqueda': row['tags_busqueda'],
            'latitude': lat,
            'longitude': lng,
            'website_primario_id': website_id,
            'state': 'aprobado',
            'tipo_id': tipo_id,
            'categoria_id': categoria_id,
            'subcategoria_id': subcategoria_id,
            'publico_ids': [(6, 0, publico_ids)],
            'momento_ids': [(6, 0, momento_ids)],
            'ambiente_ids': [(6, 0, ambiente_ids)],
            'experiencia_ids': [(6, 0, experiencia_ids)],
        }
        if image_main:
            vals['image_main'] = image_main
        if image_ids_vals:
            vals['image_ids'] = image_ids_vals
        
        existing = models.execute_kw(DB, uid, ADMIN_PASS, 'lugares.interes.historia', 'search', [[('slug', '=', row['slug'])]], {'limit': 1})
        try:
            if existing:
                models.execute_kw(DB, uid, ADMIN_PASS, 'lugares.interes.historia', 'write', [existing, vals])
                print(f"  -> Actualizado correctamente")
            else:
                models.execute_kw(DB, uid, ADMIN_PASS, 'lugares.interes.historia', 'create', [vals])
                print(f"  -> Creado correctamente")
        except Exception as e:
            print(f"  -> ERROR: {e}")
    
    print("\n[+] Reimportación completada.")


if __name__ == '__main__':
    main()
