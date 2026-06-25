# -*- coding: utf-8 -*-
"""
Tests para controladores web de Memoria Viva
"""
import json
from odoo.tests import common, tagged, HttpCase
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestMemoriaVivaWebsite(HttpCase):
    """Tests para endpoints web"""
    
    @classmethod
    def setUpClass(cls):
        super(TestMemoriaVivaWebsite, cls).setUpClass()
        
        # Usuarios
        cls.user_admin = cls.env.ref('base.user_admin')
        # base.user_demo no existe sin datos demo: creamos un usuario interno.
        cls.user_demo = cls.env['res.users'].create({
            'name': 'Test Demo User',
            'login': 'mv_test_demo_web',
            'email': 'mv_test_demo_web@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

        # Website
        cls.website = cls.env['website'].search([], limit=1)
        if not cls.website:
            cls.website = cls.env['website'].create({
                'name': 'Test Website',
                'domain': 'test.local',
            })

        # Configuración (campos website-specific memoria_viva_*).
        cls.website.write({
            'memoria_viva_permitir_comentarios': True,
        })

        # Crear tipo y categoría
        cls.tipo = cls.env['memoria.viva.tipo'].create({
            'name': 'Tipo Test Web',
        })
        cls.categoria = cls.env['memoria.viva.categoria'].create({
            'name': 'Categoria Test Web',
        })
        
        # Lugar aprobado
        cls.lugar = cls.env['memoria.viva.historia'].create({
            'name': 'Lugar Web Test',
            'description': 'Descripción web',
            'tipo_id': cls.tipo.id,
            'categoria_id': cls.categoria.id,
            'website_primario_id': cls.website.id,
            'state': 'aprobado',
            'slug': 'lugar-web-test',
        })

        # Lugar pendiente
        cls.lugar_pendiente = cls.env['memoria.viva.historia'].create({
            'name': 'Lugar Pendiente Web',
            'description': 'Pendiente',
            'website_primario_id': cls.website.id,
            'state': 'pendiente',
            'slug': 'lugar-pendiente-web',
        })
    
    # === Tests de Páginas Públicas ===
    
    def test_01_pagina_listado_accesible(self):
        """Test: Página de listado accesible públicamente"""
        self.authenticate(None, None)  # Público
        response = self.url_open('/memoria-viva')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Memoria Viva', response.content)
    
    def test_02_pagina_detalle_accesible(self):
        """Test: Página de detalle accesible para lugar aprobado"""
        self.authenticate(None, None)
        response = self.url_open(f'/memoria-viva/{self.lugar.slug}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Lugar Web Test', response.content)
    
    def test_03_pagina_detalle_lugar_pendiente_404(self):
        """Test: Lugar pendiente no debe ser visible"""
        self.authenticate(None, None)
        response = self.url_open(f'/memoria-viva/{self.lugar_pendiente.slug}')
        self.assertEqual(response.status_code, 404)
    
    def test_04_pagina_detalle_slug_invalido_404(self):
        """Test: Slug inválido debe retornar 404"""
        self.authenticate(None, None)
        response = self.url_open('/memoria-viva/slug-que-no-existe')
        self.assertEqual(response.status_code, 404)
    
    # === Tests de API JSON - Envío de Lugares ===
    
    def test_05_api_submit_lugar(self):
        """Test: Enviar lugar vía API JSON"""
        data = {
            'name': 'Nuevo Lugar API',
            'description': 'Descripción desde API',
            'tipo_id': self.tipo.id,
            'categoria_id': self.categoria.id,
            'direccion': 'Calle API 123',
            'publicador_nombre': 'Usuario API',
            'publicador_telefono': '123456789',
            'publicador_email': 'api@test.com',
        }
        
        response = self.url_open(
            '/memoria_viva/api/submit',
            data=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertTrue(result.get('success'))
        self.assertTrue(result.get('lugar_id'))
    
    def test_06_api_submit_sin_nombre(self):
        """Test: API rechaza envío sin nombre"""
        data = {
            'description': 'Sin nombre',
        }
        
        response = self.url_open(
            '/memoria_viva/api/submit',
            data=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertFalse(result.get('success'))
        self.assertIn('nombre', result.get('error', '').lower())
    
    def test_07_api_submit_con_imagen(self):
        """Test: Enviar lugar con imagen base64"""
        import base64
        # Imagen PNG de 1x1 píxel transparente
        imagen_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
        
        data = {
            'name': 'Lugar con Imagen',
            'description': 'Con imagen',
            'image_main': f'data:image/png;base64,{imagen_b64}',
            'publicador_nombre': 'Usuario Imagen',
        }
        
        response = self.url_open(
            '/memoria_viva/api/submit',
            data=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertTrue(result.get('success'))
    
    # === Tests de API de Likes ===
    
    def test_08_api_like_lugar(self):
        """Test: Dar like a un lugar"""
        response = self.url_open(
            f'/memoria-viva/like/{self.lugar.id}',
            data='{}',
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertTrue(result.get('success'))
        self.assertEqual(result.get('like_count'), 1)
    
    def test_09_api_like_dos_veces_mismo_sesion(self):
        """Test: No se puede dar like dos veces con misma sesión"""
        # Primer like
        self.url_open(
            f'/memoria-viva/like/{self.lugar.id}',
            data='{}',
            headers={'Content-Type': 'application/json'}
        )
        
        # Segundo like (misma sesión/cookie)
        response = self.url_open(
            f'/memoria-viva/like/{self.lugar.id}',
            data='{}',
            headers={'Content-Type': 'application/json'}
        )
        
        result = json.loads(response.content)
        self.assertTrue(result.get('already_liked'))
        self.assertEqual(result.get('like_count'), 1)
    
    def test_10_api_like_lugar_inexistente(self):
        """Test: Like a lugar inexistente retorna error"""
        response = self.url_open(
            '/memoria-viva/like/999999',
            data='{}',
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 404)
    
    # === Tests de API de Comentarios ===
    
    def test_11_api_enviar_comentario_logueado(self):
        """Test: Usuario logueado puede comentar"""
        self.authenticate('demo', 'demo')
        
        data = {
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario de test',
        }
        
        response = self.url_open(
            '/memoria-viva/comentario/enviar',
            data=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertTrue(result.get('success'))
        self.assertEqual(result.get('estado'), 'aprobado')
    
    def test_12_api_enviar_comentario_sin_login(self):
        """Test: Usuario anónimo no puede comentar"""
        self.authenticate(None, None)
        
        data = {
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario anónimo',
        }
        
        response = self.url_open(
            '/memoria-viva/comentario/enviar',
            data=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        
        # Debe redirigir a login o retornar 403
        self.assertIn(response.status_code, [302, 403])
    
    def test_13_api_listar_comentarios(self):
        """Test: Listar comentarios de un lugar"""
        # Crear comentarios
        Comentario = self.env['memoria.viva.comentario'].sudo()
        for i in range(3):
            Comentario.create({
                'lugar_id': self.lugar.id,
                'contenido': f'Comentario {i}',
                'autor_id': self.user_demo.id,
                'estado': 'aprobado',
            })
        
        self.authenticate(None, None)
        response = self.url_open(f'/memoria-viva/comentario/listar?lugar_id={self.lugar.id}')
        
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertTrue(result.get('success'))
        self.assertEqual(len(result.get('comentarios', [])), 3)
    
    def test_14_api_comentario_con_moderacion(self):
        """Test: Comentario con palabra prohibida queda pendiente"""
        # Crear palabra prohibida
        self.env['memoria.viva.palabra.prohibida'].create({'name': 'spam'})
        
        self.authenticate('demo', 'demo')
        
        data = {
            'lugar_id': self.lugar.id,
            'contenido': 'Esto es spam',
        }
        
        response = self.url_open(
            '/memoria-viva/comentario/enviar',
            data=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertTrue(result.get('success'))
        self.assertEqual(result.get('estado'), 'pendiente')
        self.assertIn('moderación', result.get('mensaje', '').lower())
    
    def test_15_api_respuesta_comentario(self):
        """Test: Responder a un comentario"""
        # Crear comentario padre
        Comentario = self.env['memoria.viva.comentario'].sudo()
        padre = Comentario.create({
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario padre',
            'autor_id': self.user_demo.id,
            'estado': 'aprobado',
        })
        
        self.authenticate('admin', 'admin')
        
        data = {
            'lugar_id': self.lugar.id,
            'contenido': 'Respuesta al comentario',
            'parent_id': padre.id,
        }
        
        response = self.url_open(
            '/memoria-viva/comentario/enviar',
            data=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertTrue(result.get('success'))
    
    # === Tests de Filtros y Búsqueda ===
    
    def test_16_buscar_por_texto(self):
        """Test: Buscar lugares por texto"""
        self.authenticate(None, None)
        response = self.url_open('/memoria-viva?search=Web+Test')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Lugar Web Test', response.content)
    
    def test_17_filtrar_por_tipo(self):
        """Test: Filtrar lugares por tipo"""
        self.authenticate(None, None)
        response = self.url_open(f'/memoria-viva?tipo={self.tipo.id}')
        self.assertEqual(response.status_code, 200)
    
    def test_18_filtrar_por_categoria(self):
        """Test: Filtrar lugares por categoría"""
        self.authenticate(None, None)
        response = self.url_open(f'/memoria-viva?categoria={self.categoria.id}')
        self.assertEqual(response.status_code, 200)
    
    # === Tests de Anuncios ===
    
    def test_19_anuncio_visible_en_listado(self):
        """Test: Anuncio activo visible en listado"""
        self.env['memoria.viva.anuncio'].create({
            'name': 'Anuncio Test',
            'tipo': 'banner',
            'titulo': 'Título Visible',
            'website_primario_id': self.website.id,
            'state': 'active',
        })
        
        self.authenticate(None, None)
        response = self.url_open('/memoria-viva')
        self.assertEqual(response.status_code, 200)
    
    # === Tests de Configuración en Frontend ===
    
    def test_20_configuracion_formulario_visible(self):
        """Test: Configuración afecta visibilidad del formulario"""
        self.authenticate(None, None)
        response = self.url_open('/memoria-viva')
        self.assertEqual(response.status_code, 200)

    # === Tests de Regresión (Bug 2) ===

    def test_21_oe_structure_tiene_id_unico(self):
        """Regresión Bug 2: el dropzone oe_structure del listado tiene id único y estable.

        Sin un id estable en el oe_structure, Odoo no guarda el contenido del
        Website Builder en un registro propio (copy-on-write) y se resetea en
        cada actualización del módulo (-u memoria_viva).
        """
        view = self.env['ir.ui.view'].search(
            [('key', '=', 'memoria_viva.memoria_viva_list')], limit=1
        )
        self.assertTrue(view, "No se encontró la vista memoria_viva.memoria_viva_list")
        self.assertIn(
            'oe_structure_memoria_viva_top', view.arch,
            "El dropzone oe_structure debe tener id='oe_structure_memoria_viva_top'"
        )

    def test_22_oe_structure_dropzone_canonica_vacia(self):
        """Regresión Bug 2: el dropzone oe_structure es canónico (vacío).

        El placeholder hardcodeado (<section> con "Haz clic en 'Editar'...") junto
        con data-editor-message manual provocaba un doble placeholder ("campos
        duplicados") y un DOM no estándar que rompía el guardado copy-on-write del
        Website Builder (spinner infinito al soltar bloques). La forma canónica es
        un <div class="oe_structure" id="..."/> VACÍO; Odoo añade su propio mensaje.
        """
        from lxml import etree

        view = self.env['ir.ui.view'].search(
            [('key', '=', 'memoria_viva.memoria_viva_list')], limit=1
        )
        self.assertTrue(view, "No se encontró la vista memoria_viva.memoria_viva_list")

        tree = etree.fromstring(view.arch.encode('utf-8'))
        dropzones = tree.xpath("//div[@id='oe_structure_memoria_viva_top']")
        self.assertEqual(
            len(dropzones), 1,
            "Debe existir exactamente un dropzone oe_structure_memoria_viva_top"
        )
        dropzone = dropzones[0]

        # No debe arrastrar el placeholder hardcodeado dentro del dropzone.
        self.assertEqual(
            len(dropzone.getchildren()), 0,
            "El dropzone oe_structure debe quedar VACÍO (canónico), sin "
            "<section> placeholder hardcodeado dentro"
        )
        # No debe usar data-editor-message manual: Odoo pone su propio mensaje.
        self.assertNotIn(
            'data-editor-message', dropzone.attrib,
            "El dropzone no debe llevar data-editor-message manual"
        )
        # El placeholder textual ya no debe estar en el arch.
        self.assertNotIn(
            "Haz clic en 'Editar' para añadir contenido aquí", view.arch,
            "El texto placeholder hardcodeado debe haberse eliminado"
        )


@tagged('post_install', '-at_install')
class TestMemoriaVivaXmlRpc(common.TransactionCase):
    """Tests para acceso vía XML-RPC"""
    
    @classmethod
    def setUpClass(cls):
        super(TestMemoriaVivaXmlRpc, cls).setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        if not cls.website:
            cls.website = cls.env['website'].create({
                'name': 'Test Website',
                'domain': 'test.local',
            })
    
    def test_01_xmlrpc_search_read_lugares(self):
        """Test: Buscar y leer lugares vía XML-RPC"""
        # Simular llamada XML-RPC
        Lugar = self.env['memoria.viva.historia']
        lugares = Lugar.search_read(
            [('state', '=', 'aprobado')],
            ['name', 'description', 'slug', 'state'],
            limit=10
        )
        self.assertIsInstance(lugares, list)
    
    def test_02_xmlrpc_crear_lugar(self):
        """Test: Crear lugar vía XML-RPC"""
        Lugar = self.env['memoria.viva.historia']
        lugar_id = Lugar.create({
            'name': 'Lugar XML-RPC',
            'description': 'Creado vía XML-RPC',
            'website_primario_id': self.website.id,
            'state': 'aprobado',
        })
        self.assertTrue(lugar_id.id)
    
    def test_03_xmlrpc_actualizar_lugar(self):
        """Test: Actualizar lugar vía XML-RPC"""
        Lugar = self.env['memoria.viva.historia']
        lugar = Lugar.create({
            'name': 'Lugar para Actualizar',
            'description': 'Original',
            'website_primario_id': self.website.id,
        })
        
        lugar.write({'description': 'Actualizado'})
        self.assertEqual(lugar.description, 'Actualizado')
    
    def test_04_xmlrpc_buscar_comentarios(self):
        """Test: Buscar comentarios vía XML-RPC"""
        Comentario = self.env['memoria.viva.comentario']
        comentarios = Comentario.search_read(
            [('estado', '=', 'aprobado')],
            ['contenido', 'autor_id', 'lugar_id', 'estado'],
            limit=10
        )
        self.assertIsInstance(comentarios, list)
    
    def test_05_xmlrpc_leer_config_website(self):
        """Test: Leer la config de Memoria Viva (campos website-specific)."""
        # La config ya no es un modelo propio: son campos memoria_viva_* en
        # el website, legibles vía ORM/XML-RPC.
        self.website.write({'memoria_viva_permitir_comentarios': True})
        self.assertTrue(self.website.memoria_viva_permitir_comentarios)
        self.assertIn(
            'memoria_viva_permitir_comentarios', self.website._fields)
