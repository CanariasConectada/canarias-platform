"""
Hooks for business_category_hierarchy module.
Creates initial categories without ir.model.data entries.
"""
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Initial categories - created only if they don't exist, without ir.model.data
# Format: (name, parent_name or None)
DEFAULT_CATEGORIES = [
    # ALIMENTACIÓN
    ('Alimentación', None),
    ('Asadero de pollos', 'Alimentación'),
    ('Bazar', 'Alimentación'),
    ('Carnicería', 'Alimentación'),
    ('Comida para llevar', 'Alimentación'),
    ('Frutería', 'Alimentación'),
    ('Minimercado', 'Alimentación'),
    ('Panadería', 'Alimentación'),
    ('Pescadería', 'Alimentación'),
    ('Supermercado', 'Alimentación'),
    # ANIMALES Y FLORISTERÍA
    ('Animales y floristería', None),
    ('Floristería', 'Animales y floristería'),
    ('Peluquería/Estética de Animales', 'Animales y floristería'),
    ('Tienda de animales', 'Animales y floristería'),
    ('Veterinario', 'Animales y floristería'),
    # COMERCIO
    ('Comercio', None),
    ('Abierto 24 Horas', 'Comercio'),
    ('Arte/Artesanía', 'Comercio'),
    ('Calzado', 'Comercio'),
    ('Compro oro', 'Comercio'),
    ('Estanco de Loterías', 'Comercio'),
    ('Ferretería', 'Comercio'),
    ('Joyería', 'Comercio'),
    ('Librería', 'Comercio'),
    ('Mercería', 'Comercio'),
    ('Papelería', 'Comercio'),
    ('Pirotecnia', 'Comercio'),
    ('Productos de Estética y Perfumería', 'Comercio'),
    ('Sex Shop', 'Comercio'),
    ('Surf', 'Comercio'),
    ('Tabaquería', 'Comercio'),
    ('Tienda Cuadros/Encuadernación', 'Comercio'),
    ('Tienda de artículos de hostelería', 'Comercio'),
    ('Tienda de artículos para el hogar', 'Comercio'),
    ('Tienda de costura', 'Comercio'),
    ('Tienda de deporte', 'Comercio'),
    ('Tienda de electricidad / telecomunicaciones', 'Comercio'),
    ('Tienda de gafas', 'Comercio'),
    ('Tienda de iluminación', 'Comercio'),
    ('Tienda de juguetes', 'Comercio'),
    ('Tienda de manualidades', 'Comercio'),
    ('Tienda de máquinas de coser', 'Comercio'),
    ('Tienda de moda', 'Comercio'),
    ('Tienda de muebles', 'Comercio'),
    ('Tienda de pesca', 'Comercio'),
    ('Tienda de segunda mano', 'Comercio'),
    ('Tienda especializada en música y cine', 'Comercio'),
    ('Venta de material eléctrico', 'Comercio'),
    # DEPORTE, SALUD Y BELLEZA
    ('Deporte, salud y belleza', None),
    ('Calzado ortopédico', 'Deporte, salud y belleza'),
    ('Centro de artes marciales', 'Deporte, salud y belleza'),
    ('Centro de masajes', 'Deporte, salud y belleza'),
    ('Ciclismo', 'Deporte, salud y belleza'),
    ('Clases de Pilates', 'Deporte, salud y belleza'),
    ('Clases de Surf', 'Deporte, salud y belleza'),
    ('Clases de Yoga', 'Deporte, salud y belleza'),
    ('Clínica dental', 'Deporte, salud y belleza'),
    ('Depilación', 'Deporte, salud y belleza'),
    ('Estética', 'Deporte, salud y belleza'),
    ('Farmacia', 'Deporte, salud y belleza'),
    ('Fisioterapia', 'Deporte, salud y belleza'),
    ('Gimnasio', 'Deporte, salud y belleza'),
    ('Herbolario', 'Deporte, salud y belleza'),
    ('Manicura-Pedicura-Estética Uñas', 'Deporte, salud y belleza'),
    ('Óptica', 'Deporte, salud y belleza'),
    ('Peluquería', 'Deporte, salud y belleza'),
    ('Salón de tatuaje', 'Deporte, salud y belleza'),
    ('Terapia', 'Deporte, salud y belleza'),
    ('Tienda de fajas postquirúrjicas', 'Deporte, salud y belleza'),
    ('Tienda de ortopedia', 'Deporte, salud y belleza'),
    # INFORMÁTICA Y TELEFONÍA
    ('Informática y telefonía', None),
    ('Equipos y periféricos', 'Informática y telefonía'),
    ('Marketing Digital', 'Informática y telefonía'),
    ('Páginas Web', 'Informática y telefonía'),
    ('Reparación de equipos', 'Informática y telefonía'),
    ('Software', 'Informática y telefonía'),
    ('Tienda de informática', 'Informática y telefonía'),
    ('Tienda de móviles', 'Informática y telefonía'),
    ('Venta y reparación de móviles', 'Informática y telefonía'),
    # RESTAURACIÓN/OCIO
    ('Restauración/Ocio', None),
    ('Bar', 'Restauración/Ocio'),
    ('Cafetería', 'Restauración/Ocio'),
    ('Churrería', 'Restauración/Ocio'),
    ('Discotecas', 'Restauración/Ocio'),
    ('Dulcería', 'Restauración/Ocio'),
    ('Grow Shop', 'Restauración/Ocio'),
    ('Hamburguesería', 'Restauración/Ocio'),
    ('Heladería', 'Restauración/Ocio'),
    ('Pet Friendly', 'Restauración/Ocio'),
    ('Piscolabis', 'Restauración/Ocio'),
    ('Pizzería', 'Restauración/Ocio'),
    ('Pub', 'Restauración/Ocio'),
    ('Restaurante', 'Restauración/Ocio'),
    ('Salón de baile', 'Restauración/Ocio'),
    ('Sitios de Apuestas', 'Restauración/Ocio'),
    # SERVICIOS
    ('Servicios', None),
    ('Abogados', 'Servicios'),
    ('Agencias de viaje', 'Servicios'),
    ('Alojamientos', 'Servicios'),
    ('Asesoría', 'Servicios'),
    ('Autolavado', 'Servicios'),
    ('Autoservicio', 'Servicios'),
    ('Banco', 'Servicios'),
    ('Carpintería', 'Servicios'),
    ('Cerrajero', 'Servicios'),
    ('Copistería', 'Servicios'),
    ('Diseño y rotulación', 'Servicios'),
    ('Distribuidor', 'Servicios'),
    ('Electricista', 'Servicios'),
    ('Entrega de Paquetes', 'Servicios'),
    ('Especialistas en cristales', 'Servicios'),
    ('Eventos-Salas', 'Servicios'),
    ('Fontanería', 'Servicios'),
    ('Impresión y Fotocopias', 'Servicios'),
    ('Inmobiliaria', 'Servicios'),
    ('Instalaciones de persianas', 'Servicios'),
    ('Lavandería / Costura', 'Servicios'),
    ('Locutorio', 'Servicios'),
    ('Médicos. Ginecología/obstetria', 'Servicios'),
    ('Mudanzas', 'Servicios'),
    ('Niños / Puericultura', 'Servicios'),
    ('Parking', 'Servicios'),
    ('Reformas', 'Servicios'),
    ('Salones de conferencias', 'Servicios'),
    ('Seguridad y vigilancia', 'Servicios'),
    ('Seguros', 'Servicios'),
    ('Servicio técnico', 'Servicios'),
    ('Tapicería', 'Servicios'),
    ('Tintorería', 'Servicios'),
    # VEHÍCULOS Y BICICLETAS
    ('Vehículos y Bicicletas', None),
    ('Autorepuestos', 'Vehículos y Bicicletas'),
    ('Bicicletas y Patinetas', 'Vehículos y Bicicletas'),
    ('Coche', 'Vehículos y Bicicletas'),
    ('Moto', 'Vehículos y Bicicletas'),
    ('Neumáticos', 'Vehículos y Bicicletas'),
]


def post_init_hook(cr, registry):
    """Create initial categories without ir.model.data entries."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Category = env['business.category']
    
    _logger.info("Creating initial business categories (if not exist)...")
    
    # First pass: create parent categories
    parent_cache = {}
    for name, parent_name in DEFAULT_CATEGORIES:
        if parent_name is None:
            existing = Category.search([('name', '=', name), ('parent_id', '=', False)], limit=1)
            if not existing:
                cat = Category.create({'name': name})
                parent_cache[name] = cat.id
                _logger.info(f"Created category: {name}")
            else:
                parent_cache[name] = existing.id
    
    # Second pass: create child categories
    for name, parent_name in DEFAULT_CATEGORIES:
        if parent_name is not None:
            parent_id = parent_cache.get(parent_name)
            if not parent_id:
                parent = Category.search([('name', '=', parent_name), ('parent_id', '=', False)], limit=1)
                if parent:
                    parent_id = parent.id
                    parent_cache[parent_name] = parent_id
            
            if parent_id:
                existing = Category.search([('name', '=', name), ('parent_id', '=', parent_id)], limit=1)
                if not existing:
                    Category.create({'name': name, 'parent_id': parent_id})
                    _logger.info(f"Created subcategory: {name}")
    
    _logger.info("Business categories initialization complete")
