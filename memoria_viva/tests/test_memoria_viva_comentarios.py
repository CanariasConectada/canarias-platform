# -*- coding: utf-8 -*-
"""
Tests para el sistema de comentarios de Memoria Viva
"""
from odoo.tests import common, tagged
from odoo.exceptions import AccessError, ValidationError


@tagged('post_install', '-at_install')
class TestMemoriaVivaComentarios(common.TransactionCase):
    """Tests para comentarios y moderación"""
    
    @classmethod
    def setUpClass(cls):
        super(TestMemoriaVivaComentarios, cls).setUpClass()
        
        # Usuarios
        cls.user_admin = cls.env.ref('base.user_admin')
        # base.user_demo no existe sin datos demo: creamos un usuario interno.
        cls.user_demo = cls.env['res.users'].create({
            'name': 'Test Demo User',
            'login': 'mv_test_demo_coment',
            'email': 'mv_test_demo_coment@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.user_portal = cls.env['res.users'].create({
            'name': 'Test Portal',
            'login': 'test_portal',
            'groups_id': [(4, cls.env.ref('base.group_portal').id)],
        })
        
        # Website
        cls.website = cls.env['website'].search([], limit=1)
        if not cls.website:
            cls.website = cls.env['website'].create({
                'name': 'Test Website',
                'domain': 'test.local',
            })
        
        # Configuración con comentarios habilitados (campos website-specific).
        cls.website.write({
            'memoria_viva_permitir_comentarios': True,
        })

        # Lugar de prueba
        cls.lugar = cls.env['memoria.viva.historia'].create({
            'name': 'Lugar con Comentarios',
            'description': 'Test de comentarios',
            'website_primario_id': cls.website.id,
            'state': 'aprobado',
        })
        
        # Modelos
        cls.Comentario = cls.env['memoria.viva.comentario']
        cls.PalabraProhibida = cls.env['memoria.viva.palabra.prohibida']
    
    # === Tests de Creación de Comentarios ===
    
    def test_01_crear_comentario_simple(self):
        """Test: Crear un comentario básico"""
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Este es un comentario de prueba',
            'autor_id': self.user_demo.id,
        })
        
        self.assertTrue(comentario.id)
        self.assertEqual(comentario.lugar_id.id, self.lugar.id)
        self.assertEqual(comentario.contenido, 'Este es un comentario de prueba')
        self.assertEqual(comentario.autor_id.id, self.user_demo.id)
    
    def test_02_comentario_aprobado_por_defecto(self):
        """Test: Comentario se aprueba si no tiene palabras prohibidas"""
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario limpio y apropiado',
            'autor_id': self.user_demo.id,
        })
        
        self.assertEqual(comentario.estado, 'aprobado')
        self.assertFalse(comentario.contiene_palabras_prohibidas)
    
    def test_03_comentario_pendiente_con_palabra_prohibida(self):
        """Test: Comentario con palabra prohibida queda pendiente"""
        # Crear palabra prohibida
        self.PalabraProhibida.create({'name': 'spam'})
        
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Este es un mensaje spam',
            'autor_id': self.user_demo.id,
        })
        
        self.assertEqual(comentario.estado, 'pendiente')
        self.assertTrue(comentario.contiene_palabras_prohibidas)
    
    def test_04_comentario_case_insensitive(self):
        """Test: Detección de palabras prohibidas sin importar mayúsculas"""
        self.PalabraProhibida.create({'name': 'INSULTO'})
        
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Esto es un insulto mayúscula',
            'autor_id': self.user_demo.id,
        })
        
        self.assertEqual(comentario.estado, 'pendiente')
    
    def test_05_palabra_prohibida_inactiva(self):
        """Test: Palabra prohibida inactiva no bloquea"""
        self.PalabraProhibida.create({
            'name': 'bloqueada',
            'active': False,
        })
        
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Esta palabra bloqueada está inactiva',
            'autor_id': self.user_demo.id,
        })
        
        self.assertEqual(comentario.estado, 'aprobado')
    
    # === Tests de Respuestas Anidadas ===
    
    def test_06_crear_respuesta(self):
        """Test: Crear respuesta a un comentario"""
        # Comentario padre
        padre = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario padre',
            'autor_id': self.user_demo.id,
        })
        
        # Respuesta
        respuesta = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Respuesta al comentario',
            'autor_id': self.user_admin.id,
            'parent_id': padre.id,
        })
        
        self.assertEqual(respuesta.parent_id.id, padre.id)
        self.assertEqual(padre.respuesta_ids.ids, [respuesta.id])
    
    def test_07_comentario_tiene_respuestas(self):
        """Test: Un comentario expone sus respuestas (respuesta_ids)."""
        padre = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Padre',
            'autor_id': self.user_demo.id,
        })

        self.assertFalse(padre.respuesta_ids)

        self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Hijo',
            'autor_id': self.user_demo.id,
            'parent_id': padre.id,
        })

        padre.invalidate_recordset()
        self.assertTrue(padre.respuesta_ids)
    
    def test_08_maximo_nivel_anidamiento(self):
        """Test: Solo se permite 1 nivel de respuestas"""
        padre = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Nivel 0',
            'autor_id': self.user_demo.id,
        })
        
        hijo = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Nivel 1',
            'autor_id': self.user_demo.id,
            'parent_id': padre.id,
        })
        
        # Intentar crear nieto (debería fallar)
        with self.assertRaises(ValidationError):
            self.Comentario.sudo().create({
                'lugar_id': self.lugar.id,
                'contenido': 'Nivel 2 - no permitido',
                'autor_id': self.user_demo.id,
                'parent_id': hijo.id,
            })
    
    # === Tests de Moderación ===
    
    def test_09_aprobar_comentario(self):
        """Test: Aprobar un comentario pendiente"""
        self.PalabraProhibida.create({'name': 'moderar'})
        
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario para moderar',
            'autor_id': self.user_demo.id,
        })
        
        self.assertEqual(comentario.estado, 'pendiente')

        comentario.action_aprobar()
        self.assertEqual(comentario.estado, 'aprobado')

    def test_10_rechazar_comentario(self):
        """Test: Rechazar un comentario"""
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario rechazable',
            'autor_id': self.user_demo.id,
            'estado': 'pendiente',
        })

        comentario.action_rechazar()
        self.assertEqual(comentario.estado, 'rechazado')
    
    # === Tests de Obtención de Comentarios ===
    
    def test_11_get_comentarios_aprobados(self):
        """Test: Obtener solo comentarios aprobados"""
        # Crear comentarios
        self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Aprobado 1',
            'autor_id': self.user_demo.id,
            'estado': 'aprobado',
        })
        self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Aprobado 2',
            'autor_id': self.user_demo.id,
            'estado': 'aprobado',
        })
        self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Pendiente',
            'autor_id': self.user_demo.id,
            'estado': 'pendiente',
        })
        
        comentarios = self.Comentario.get_comentarios_aprobados(self.lugar.id)
        self.assertEqual(len(comentarios), 2)
        
        for c in comentarios:
            self.assertEqual(c['estado'], 'aprobado')
    
    def test_12_get_comentarios_con_respuestas(self):
        """Test: Obtener comentarios con sus respuestas"""
        padre = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Padre visible',
            'autor_id': self.user_demo.id,
            'estado': 'aprobado',
        })
        
        self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Respuesta visible',
            'autor_id': self.user_admin.id,
            'parent_id': padre.id,
            'estado': 'aprobado',
        })
        
        comentarios = self.Comentario.get_comentarios_aprobados(self.lugar.id)
        comentarios_con_respuestas = [c for c in comentarios if c.get('respuestas')]
        self.assertTrue(len(comentarios_con_respuestas) > 0)
    
    # === Tests de Permisos ===
    
    def test_13_usuario_no_puede_editar_otro_comentario(self):
        """Test: Usuario no puede editar comentario de otro"""
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario de demo',
            'autor_id': self.user_demo.id,
        })
        
        # Intentar editar como admin (otro usuario)
        with self.assertRaises(AccessError):
            comentario.with_user(self.user_admin).write({
                'contenido': 'Hackeado por admin'
            })
    
    # === Tests de Autor ===
    
    def test_14_autor_nombre_computado(self):
        """Test: Nombre del autor computado correctamente"""
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Test autor',
            'autor_id': self.user_demo.id,
        })
        
        self.assertEqual(comentario.autor_nombre, self.user_demo.name)
    
    def test_15_autor_imagen(self):
        """Test: Imagen del autor (avatar)"""
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Test imagen',
            'autor_id': self.user_demo.id,
        })
        
        # El campo autor_imagen es un related al avatar del usuario
        self.assertIn('autor_imagen', comentario._fields)
    
    # === Tests de Palabras Prohibidas ===
    
    def test_16_crear_palabra_prohibida(self):
        """Test: Crear lista de palabras prohibidas"""
        palabra = self.PalabraProhibida.create({
            'name': 'palabra_test',
        })
        
        self.assertTrue(palabra.id)
        self.assertTrue(palabra.active)
    
    def test_17_buscar_palabras_prohibidas_activas(self):
        """Test: Buscar solo palabras prohibidas activas"""
        self.PalabraProhibida.create({'name': 'activa1'})
        self.PalabraProhibida.create({'name': 'activa2'})
        self.PalabraProhibida.create({'name': 'inactiva', 'active': False})
        
        activas = self.PalabraProhibida.search([('active', '=', True)])
        self.assertEqual(len(activas), 2)
    
    # === Tests de Contadores ===
    
    def test_18_contador_comentarios_lugar(self):
        """Test: Contador de comentarios en el lugar"""
        # Crear múltiples comentarios aprobados
        for i in range(5):
            self.Comentario.sudo().create({
                'lugar_id': self.lugar.id,
                'contenido': f'Comentario {i}',
                'autor_id': self.user_demo.id,
                'estado': 'aprobado',
            })
        
        contador = self.Comentario.sudo().search_count([
            ('lugar_id', '=', self.lugar.id),
            ('estado', '=', 'aprobado')
        ])
        
        self.assertEqual(contador, 5)
    
    # === Tests de Eliminar ===
    
    def test_19_eliminar_comentario_cascade_respuestas(self):
        """Test: Al eliminar padre, se eliminan respuestas"""
        padre = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Padre a eliminar',
            'autor_id': self.user_demo.id,
        })
        
        hijo = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Hijo',
            'autor_id': self.user_demo.id,
            'parent_id': padre.id,
        })
        
        hijo_id = hijo.id
        padre.unlink()
        
        # Verificar que el hijo también fue eliminado
        hijo_existe = self.Comentario.search([('id', '=', hijo_id)])
        self.assertFalse(hijo_existe)
