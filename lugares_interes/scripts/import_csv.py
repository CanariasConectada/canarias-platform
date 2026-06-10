#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de importación de Lugares de Interés desde CSV + imágenes ZIP.
Uso: python3 import_csv.py
"""
import csv
import os
import sys
import base64
import zipfile
import tempfile
import xmlrpc.client

# Configuración
ODOO_URL = 'http://localhost:8069'
DB = 'canarias_conectada'
ADMIN_USER = 'miguelangel1074.gc@gmail.com'
ADMIN_PASS = 'gtMnLgDxbw9NO71C'  # Actualizar si es necesario

CSV_PATH = '/home/odoo/lugares_de_interes_importacion/lugares-20260505-V1.0.csv'
ZIP_PATH = '/home/odoo/lugares_de_interes_importacion/ANTIGUAS.zip'

# Mapeo de barrio a website_id
BARRIO_TO_WEBSITE = {
    'Guanarteme': 229,
    'Tamaraceite': 231,
    'Lomo Los Frailes': 230,
}
DEFAULT_WEBSITE_ID = 228  # Canarias Conectada


def connect():
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(DB, ADMIN_USER, ADMIN_PASS, {})
    if not uid:
        raise Exception("Autenticación fallida")
    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    return uid, models


def get_or_create_tag(models, uid, model, name):
    """Busca o crea un tag Many2many"""
    tag_id = models.execute_kw(DB, uid, ADMIN_PASS, model, 'search', [[('name', '=', name)]], {'limit': 1})
    if tag_id:
        return tag_id[0]
    return models.execute_kw(DB, uid, ADMIN_PASS, model, 'create', [{'name': name}])


def get_or_create_category(models, uid, model, name, parent_id=None):
    """Busca o crea tipo/categoría/subcategoría"""
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


def find_images(extract_dir, lugar_id):
    """Busca imágenes para un lugar ID"""
    folder = os.path.join(extract_dir, 'ANTIGUAS', str(lugar_id), '_antiguas')
    if not os.path.isdir(folder):
        return []
    files = sorted([f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
    # Ignorar streetview, usar solo gmaps
    files = [f for f in files if 'streetview' not in f.lower()]
    return [os.path.join(folder, f) for f in sorted(files)]


def main():
    print("[+] Conectando a Odoo...")
    uid, models = connect()
    print(f"[+] Autenticado como UID {uid}")

    # Extraer ZIP
    extract_dir = tempfile.mkdtemp(prefix='lugares_interes_')
    print(f"[+] Extrayendo ZIP a {extract_dir}...")
    with zipfile.ZipFile(ZIP_PATH, 'r') as z:
        z.extractall(extract_dir)

    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    print(f"[+] Total de registros CSV: {total}")

    for idx, row in enumerate(rows, 1):
        lugar_id = int(row['id'])
        name = row['nombre']
        slug = row['slug']
        barrio = row['barrio']
        ciudad = row['ciudad']
        direccion = row['direccion']
        coordenadas = row['coordenadas']
        descripcion_corta = row['descripcion_corta']
        descripcion_larga = row['descripcion_larga']
        horario = row['horario']
        tags_busqueda = row['tags_busqueda']

        # Coordenadas
        lat, lng = None, None
        if coordenadas and '|' in coordenadas:
            try:
                lat, lng = map(float, coordenadas.split('|'))
            except ValueError:
                pass

        # Website
        website_id = BARRIO_TO_WEBSITE.get(barrio, DEFAULT_WEBSITE_ID)

        # Tipo, Categoría, Subcategoría
        tipo_name = row['tipo'].strip()
        categoria_name = row['categoria'].strip()
        subcategoria_name = row['subcategoria'].strip()

        tipo_id = get_or_create_category(models, uid, 'lugares.interes.tipo', tipo_name) if tipo_name else None
        categoria_id = get_or_create_category(models, uid, 'lugares.interes.categoria', categoria_name, tipo_id) if categoria_name else None
        subcategoria_id = get_or_create_category(models, uid, 'lugares.interes.subcategoria', subcategoria_name, categoria_id) if subcategoria_name else None

        # Tags Many2many
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

        # Imágenes
        image_paths = find_images(extract_dir, lugar_id)
        image_main = None
        image_ids_vals = []
        if image_paths:
            with open(image_paths[0], 'rb') as img_f:
                image_main = base64.b64encode(img_f.read()).decode('utf-8')
            for seq, path in enumerate(image_paths[1:], 1):
                with open(path, 'rb') as img_f:
                    img_b64 = base64.b64encode(img_f.read()).decode('utf-8')
                image_ids_vals.append((0, 0, {
                    'sequence': seq,
                    'name': os.path.basename(path),
                    'image': img_b64,
                }))

        # Preparar vals
        vals = {
            'name': name,
            'slug': slug,
            'barrio': barrio,
            'ciudad': ciudad,
            'direccion': direccion,
            'description': descripcion_corta,
            'descripcion_larga': descripcion_larga,
            'horario': horario,
            'tags_busqueda': tags_busqueda,
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

        # Verificar si ya existe
        existing = models.execute_kw(DB, uid, ADMIN_PASS, 'lugares.interes.historia', 'search', [[('slug', '=', slug)]], {'limit': 1})
        try:
            if existing:
                print(f"[{idx}/{total}] Actualizando: {name}")
                models.execute_kw(DB, uid, ADMIN_PASS, 'lugares.interes.historia', 'write', [existing, vals])
            else:
                print(f"[{idx}/{total}] Creando: {name}")
                models.execute_kw(DB, uid, ADMIN_PASS, 'lugares.interes.historia', 'create', [vals])
        except Exception as e:
            print(f"[{idx}/{total}] ERROR en {name}: {e}")
            continue

    print("[+] Importación completada.")


if __name__ == '__main__':
    main()
