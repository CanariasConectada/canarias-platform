# -*- coding: utf-8 -*-
"""Tests de la configuración de Memoria Viva (res.config.settings + website).

Regresión del Bug 1: antes la acción de "Ajustes" abría el formulario del
singleton memoria.viva.settings en modo creación, así que cada guardado creaba
un registro nuevo mientras el frontend leía el más antiguo → nada se guardaba y
no se podía desactivar el anuncio. Ahora la config son campos website-specific
editados vía res.config.settings; estos tests verifican que SÍ persisten.
"""
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestMemoriaVivaSettings(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        if not cls.website:
            cls.website = cls.env['website'].create({'name': 'Test Website'})

    def _save_config(self, **vals):
        """Simula 'Guardar' en Ajustes vía res.config.settings."""
        vals['website_id'] = self.website.id
        settings = self.env['res.config.settings'].create(vals)
        settings.execute()
        self.website.invalidate_recordset()

    def test_10_modelo_antiguo_eliminado(self):
        """El singleton problemático ya no existe en el registro."""
        self.assertNotIn('memoria.viva.settings', self.env)

    def test_20_anuncio_se_puede_desactivar(self):
        """Regresión directa: desactivar el anuncio persiste (antes no)."""
        self.website.memoria_viva_anuncio_activo = True
        self._save_config(memoria_viva_anuncio_activo=False)
        self.assertFalse(
            self.website.memoria_viva_anuncio_activo,
            "Al guardar Ajustes el anuncio debe quedar desactivado")

        # Y se puede volver a activar (ida y vuelta).
        self._save_config(memoria_viva_anuncio_activo=True)
        self.assertTrue(self.website.memoria_viva_anuncio_activo)

    def test_30_textos_y_numeros_persisten(self):
        self._save_config(
            memoria_viva_anuncio_titulo='Sorteo 2026',
            memoria_viva_anuncio_texto='Participa ya',
            memoria_viva_anuncio_color='success',
            memoria_viva_likes_cookie_days=90,
            memoria_viva_comentarios_por_pagina=25,
        )
        self.assertEqual(self.website.memoria_viva_anuncio_titulo, 'Sorteo 2026')
        self.assertEqual(self.website.memoria_viva_anuncio_texto, 'Participa ya')
        self.assertEqual(self.website.memoria_viva_anuncio_color, 'success')
        self.assertEqual(self.website.memoria_viva_likes_cookie_days, 90)
        self.assertEqual(self.website.memoria_viva_comentarios_por_pagina, 25)

    def test_40_toggles_visibilidad_formulario(self):
        self._save_config(
            memoria_viva_show_tipo=True,
            memoria_viva_show_mapa=True,
            memoria_viva_permitir_comentarios=False,
        )
        self.assertTrue(self.website.memoria_viva_show_tipo)
        self.assertTrue(self.website.memoria_viva_show_mapa)
        self.assertFalse(self.website.memoria_viva_permitir_comentarios)

    def test_50_defaults_correctos(self):
        """Un website nuevo nace con los defaults esperados."""
        nuevo = self.env['website'].new({})
        self.assertTrue(nuevo.memoria_viva_anuncio_activo)
        self.assertTrue(nuevo.memoria_viva_permitir_comentarios)
        self.assertTrue(nuevo.memoria_viva_show_reset_filters)
        self.assertEqual(nuevo.memoria_viva_likes_cookie_days, 365)
        self.assertEqual(nuevo.memoria_viva_comentarios_por_pagina, 10)
        self.assertFalse(nuevo.memoria_viva_show_tipo)

    def test_60_es_website_specific(self):
        """Cambiar la config de un website no afecta a otro (aislamiento)."""
        otro = self.env['website'].create({'name': 'Otro MV'})
        self.website.memoria_viva_anuncio_activo = True
        otro.memoria_viva_anuncio_activo = True
        self._save_config(memoria_viva_anuncio_activo=False)
        otro.invalidate_recordset()
        self.assertFalse(self.website.memoria_viva_anuncio_activo)
        self.assertTrue(
            otro.memoria_viva_anuncio_activo,
            "La config debe ser independiente por website")

    def test_70_enabled_default_false(self):
        """Un website nuevo nace con Memoria Viva deshabilitada (default)."""
        nuevo = self.env['website'].new({})
        self.assertFalse(
            nuevo.memoria_viva_enabled,
            "Por defecto ningún sitio debe tener /memoria-viva habilitada")

    def test_80_enabled_persiste_via_settings(self):
        """memoria_viva_enabled se guarda vía res.config.settings."""
        self.website.memoria_viva_enabled = False
        self._save_config(memoria_viva_enabled=True)
        self.assertTrue(
            self.website.memoria_viva_enabled,
            "Activar Memoria Viva en Ajustes debe persistir")

        self._save_config(memoria_viva_enabled=False)
        self.assertFalse(self.website.memoria_viva_enabled)

    def test_90_enabled_es_website_specific(self):
        """Habilitar Memoria Viva en un website no afecta a otro."""
        otro = self.env['website'].create({'name': 'Otro MV enabled'})
        otro.memoria_viva_enabled = False
        self._save_config(memoria_viva_enabled=True)
        otro.invalidate_recordset()
        self.assertTrue(self.website.memoria_viva_enabled)
        self.assertFalse(
            otro.memoria_viva_enabled,
            "La disponibilidad debe ser independiente por website")
