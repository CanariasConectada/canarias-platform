# -*- coding: utf-8 -*-
"""Tests de regresión de Memoria Viva que solo dependen del arch de las vistas.

Se mantienen en una clase ligera (sin setUpClass pesado) para que NO queden
atrapados por la deuda del suite legacy (que crea historias/anuncios contra un
schema antiguo). Aquí solo se lee ``ir.ui.view``.
"""
from lxml import etree

from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestMemoriaVivaRegression(common.TransactionCase):

    def _get_list_view(self):
        view = self.env['ir.ui.view'].search(
            [('key', '=', 'memoria_viva.memoria_viva_list')], limit=1
        )
        self.assertTrue(
            view, "No se encontró la vista memoria_viva.memoria_viva_list")
        return view

    def test_10_oe_structure_tiene_id_unico(self):
        """Regresión Bug 2: el dropzone oe_structure del listado tiene id único.

        Sin un id estable en el oe_structure, Odoo no guarda el contenido del
        Website Builder en un registro propio (copy-on-write) y se resetea en
        cada actualización del módulo (-u memoria_viva).
        """
        view = self._get_list_view()
        self.assertIn(
            'oe_structure_memoria_viva_top', view.arch,
            "El dropzone oe_structure debe tener id='oe_structure_memoria_viva_top'"
        )

    def test_20_oe_structure_dropzone_canonica_vacia(self):
        """Regresión Bug 2/3: el dropzone oe_structure es canónico (vacío).

        El placeholder hardcodeado (<section> con "Haz clic en 'Editar'...") junto
        con data-editor-message manual provocaba un doble placeholder ("campos
        duplicados") y un DOM no estándar que rompía el guardado copy-on-write del
        Website Builder (spinner infinito al soltar bloques). La forma canónica es
        un <div class="oe_structure" id="..."/> VACÍO; Odoo añade su propio mensaje.
        """
        view = self._get_list_view()
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

    def test_40_settings_resto_gated_por_enabled(self):
        """El resto de ajustes de Memoria Viva se ocultan si el sitio no está
        habilitado (todo depende de memoria_viva_enabled).

        El toggle "Disponibilidad del sitio" debe seguir SIEMPRE visible; los
        demás <setting> deben llevar invisible="not memoria_viva_enabled".
        """
        view = self.env.ref('memoria_viva.res_config_settings_view_form')
        arch = view.arch
        # El gate aplica al resto de ajustes (varias veces).
        self.assertGreaterEqual(
            arch.count('invisible="not memoria_viva_enabled"'), 8,
            "Los ajustes dependientes deben ocultarse cuando el sitio no está "
            "habilitado (invisible='not memoria_viva_enabled')"
        )
        # El propio toggle NO debe ocultarse a sí mismo.
        self.assertIn('memoria_viva_enabled', arch)

    def test_30_anuncio_filtro_categoria_inexistente_no_rompe(self):
        """Regresión: el badge del filtro de categoría no debe romper (IndexError).

        Antes la plantilla hacía ``[c for c in categorias if ...][0]['name']`` y
        reventaba con IndexError (500) al filtrar por una categoría sin coincidencia
        (típico de bots con ?categoria=NNN inexistente). Ahora usa ``next(.., '')``
        con guarda. Verificamos que el arch ya no contenga el acceso frágil ``[0]``.
        """
        view = self._get_list_view()
        self.assertNotIn(
            "if c['id'] == categoria_filter][0]", view.arch,
            "El acceso frágil [0] al filtrar categoría debe haberse eliminado"
        )
