# -*- coding: utf-8 -*-
"""Tests de seguridad de Memoria Viva: reglas de registro (ir.rule), grupos,
privilegios y categoría.

Cubre los dos puntos que se ven en el formulario de usuario:
1. Que las reglas/grupos FUNCIONAN (público solo ve historias aprobadas;
   el aprobador ve y edita todas; un interno normal no puede escribir).
2. Que la configuración está AGRUPADA: una sola categoría "Memoria Viva" con
   privilegios descriptivos (Historias, Comentarios, Anuncios) y sin duplicados
   huérfanos.
"""
import base64
import io

from PIL import Image

from odoo.exceptions import AccessError
from odoo.tests import common, tagged


def _png_valido():
    """Genera un PNG real con PIL (image_main es required y Odoo lo procesa a
    WebP al asignarlo; un PNG inválido/truncado rompe image_fix_orientation)."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (180, 180, 180)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue())


_PNG_1X1 = _png_valido()


@tagged("post_install", "-at_install")
class TestMemoriaVivaSecurity(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tipo = cls.env["memoria.viva.tipo"].create({"name": "Tipo Seguridad"})
        cls.categoria = cls.env["memoria.viva.categoria"].create(
            {"name": "Cat Seguridad", "tipo_id": cls.tipo.id}
        )

        def _historia(nombre, state):
            return cls.env["memoria.viva.historia"].create(
                {
                    "name": nombre,
                    "categoria_id": cls.categoria.id,
                    "image_main": _PNG_1X1,
                    "state": state,
                }
            )

        cls.historia_aprobada = _historia("Historia aprobada", "aprobado")
        cls.historia_borrador = _historia("Historia borrador", "borrador")

        # Usuario público y un interno básico (sin permisos de Memoria Viva).
        cls.public_user = cls.env.ref("base.public_user")
        cls.user_interno = cls.env["res.users"].create(
            {
                "name": "Interno MV",
                "login": "mv_sec_interno",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        # Aprobador.
        cls.user_aprobador = cls.env["res.users"].create(
            {
                "name": "Aprobador MV",
                "login": "mv_sec_aprobador",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("memoria_viva.group_memoria_viva_approver").id,
                        ],
                    )
                ],
            }
        )

    # ---- Reglas de registro (ir.rule) ----

    def test_10_publico_solo_ve_aprobadas(self):
        """La regla pública limita la lectura a historias en estado 'aprobado'."""
        Historia = self.env["memoria.viva.historia"].with_user(self.public_user)
        visibles = Historia.search(
            [("id", "in", (self.historia_aprobada + self.historia_borrador).ids)]
        )
        self.assertIn(self.historia_aprobada, visibles)
        self.assertNotIn(
            self.historia_borrador,
            visibles,
            "El público NO debe ver historias en borrador",
        )

    def test_20_aprobador_ve_todas(self):
        """El aprobador ve todas las historias, también las no aprobadas."""
        Historia = self.env["memoria.viva.historia"].with_user(self.user_aprobador)
        visibles = Historia.search(
            [("id", "in", (self.historia_aprobada + self.historia_borrador).ids)]
        )
        self.assertIn(self.historia_aprobada, visibles)
        self.assertIn(self.historia_borrador, visibles)

    def test_30_aprobador_puede_editar(self):
        """El aprobador puede escribir (regla interna perm_write=True + ACL)."""
        historia = self.historia_borrador.with_user(self.user_aprobador)
        historia.write({"name": "Editada por aprobador"})
        self.assertEqual(historia.name, "Editada por aprobador")

    def test_40_interno_normal_no_puede_escribir(self):
        """Un interno sin el grupo aprobador no puede modificar historias."""
        with self.assertRaises(AccessError):
            self.historia_borrador.with_user(self.user_interno).write(
                {"name": "Hackeada"}
            )

    # ---- Agrupación de privilegios / categoría ----

    def test_50_una_sola_categoria_canonica(self):
        """Existe una categoría 'Memoria Viva' canónica (con xmlid)."""
        categoria = self.env.ref("memoria_viva.category_memoria_viva")
        self.assertEqual(categoria.name, "Memoria Viva")

    def test_60_privilegios_descriptivos_bajo_la_categoria(self):
        """Los 3 privilegios descriptivos cuelgan de la única categoría."""
        categoria = self.env.ref("memoria_viva.category_memoria_viva")
        privs = {
            self.env.ref("memoria_viva.privilege_memoria_viva"),
            self.env.ref("memoria_viva.privilege_memoria_viva_comentarios"),
            self.env.ref("memoria_viva.privilege_memoria_viva_anuncios"),
        }
        for priv in privs:
            self.assertEqual(
                priv.category_id,
                categoria,
                "Todos los privilegios deben colgar de la categoría Memoria Viva",
            )
        self.assertEqual(
            self.env.ref("memoria_viva.privilege_memoria_viva").name, "Historias"
        )

    def test_70_grupos_asignados_a_su_privilegio(self):
        """Los 4 grupos tienen privilegio (ninguno huérfano en la UI)."""
        grupos = [
            "group_memoria_viva_approver",
            "group_memoria_viva_moderator",
            "group_memoria_viva_anuncios_editor",
            "group_memoria_viva_anuncios_manager",
        ]
        for xmlid in grupos:
            grupo = self.env.ref("memoria_viva.%s" % xmlid)
            self.assertTrue(
                grupo.privilege_id,
                "El grupo %s debe estar asignado a un privilegio" % xmlid,
            )

    def test_80_anuncios_admin_implica_editor(self):
        """Administrador de anuncios incluye los permisos de Editor."""
        admin = self.env.ref("memoria_viva.group_memoria_viva_anuncios_manager")
        editor = self.env.ref("memoria_viva.group_memoria_viva_anuncios_editor")
        self.assertIn(
            editor,
            admin.implied_ids,
            "El Administrador de anuncios debe implicar al Editor",
        )
