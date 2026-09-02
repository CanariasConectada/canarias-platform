# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""El comerciante pone su categoría, y sólo la suya.

Este camino escribe `category_id` en `res.company` con `sudo()`, porque
hacerlo con los permisos del usuario es imposible: un usuario portal recibe
`AccessError: No puede modificar 'Compañías'`. Una escalada de privilegio
vale exactamente lo que valgan sus comprobaciones, así que aquí se prueban
todas, incluidas las de abuso.
"""

import re

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestSelfServiceCategory(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env["res.company"]
        Category = cls.env["res.company.category"]

        cls.shop = Company.create({"name": "Comercio del comerciante"})
        cls.other_shop = Company.create({"name": "Comercio de OTRO"})
        cls.cat_a = Category.create({"name": "Categoría A de prueba"})
        cls.cat_b = Category.create({"name": "Categoría B de prueba"})
        # Una categoría "vista" es una carpeta: agrupa a otras y no se
        # asigna a nadie (res.company.category_id se declara con
        # domain=[("type", "=", "normal")]).
        cls.cat_view = Category.create({"name": "Carpeta de prueba", "type": "view"})
        cls.other_shop.category_id = cls.cat_b

        cls.merchant = new_test_user(
            cls.env,
            login="comerciante-autoservicio",
            groups="base.group_portal",
            company_id=cls.shop.id,
            company_ids=[(6, 0, [cls.shop.id])],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def _as_merchant(self):
        return self.env(user=self.merchant.id)["res.company"]

    # -- lo que debe funcionar ------------------------------------------
    def test_the_merchant_sets_the_category_of_their_own_shop(self):
        self._as_merchant().set_own_directory_category(self.cat_a.id)
        self.assertEqual(self.shop.category_id, self.cat_a)

    def test_the_merchant_can_clear_the_category(self):
        self.shop.category_id = self.cat_a
        self._as_merchant().set_own_directory_category(False)
        self.assertFalse(self.shop.category_id)

    def test_the_own_company_is_resolved_from_the_session(self):
        self.assertEqual(
            self._as_merchant()._get_own_company_for_directory(), self.shop
        )

    # -- lo que NO debe funcionar ----------------------------------------
    def test_calling_it_on_another_company_still_writes_only_on_your_own(self):
        """El recordset del receptor se ignora a propósito.

        Si `set_own_directory_category` respetara `self`, bastaría con
        invocarlo sobre otra compañía para recategorizar el negocio de
        cualquiera. La compañía sale de la sesión, siempre.
        """
        other = self.env(user=self.merchant.id)["res.company"].browse(
            self.other_shop.id
        )
        other.set_own_directory_category(self.cat_a.id)
        self.assertEqual(
            self.other_shop.category_id,
            self.cat_b,
            "el comercio ajeno NO debe cambiar",
        )
        self.assertEqual(self.shop.category_id, self.cat_a)

    def test_a_category_that_does_not_exist_is_rejected(self):
        with self.assertRaises(UserError):
            self._as_merchant().set_own_directory_category(999999999)

    def test_an_archived_category_is_rejected(self):
        self.cat_a.active = False
        with self.assertRaises(UserError):
            self._as_merchant().set_own_directory_category(self.cat_a.id)

    def test_a_malformed_category_id_is_rejected_as_user_error(self):
        """Lo que llega de un POST puede ser cualquier cosa, y no puede reventar.

        `int("abc")` lanza ValueError, y el controlador sólo captura
        AccessError y UserError: un valor con basura se escapaba como un 500
        en vez de acabar en el redirect "?error=1" que sí está diseñado. Se
        prueba también "1.5": `int()` lo truncaría a otra categoría
        DISTINTA de la pedida, que es peor que fallar.
        """
        self.shop.category_id = self.cat_a
        for value in ("abc", "1.5", "  ", "1e3", "3,5", 1.5, {"id": 1}):
            with self.subTest(value=value):
                with self.assertRaises(UserError):
                    self._as_merchant().set_own_directory_category(value)
                self.assertEqual(
                    self.shop.category_id,
                    self.cat_a,
                    "un valor con basura no debe escribir nada",
                )

    def test_the_empty_value_of_the_form_clears_instead_of_failing(self):
        """La opción "— Sin categoría —" del formulario manda "" y debe limpiar.

        Es el contrario del test de arriba: "" no es basura, es el valor con
        el que el desplegable dice "ninguna". Se fija aquí para que endurecer
        la validación no convierta en error lo que es una opción legítima.
        """
        self.shop.category_id = self.cat_a
        self._as_merchant().set_own_directory_category("")
        self.assertFalse(self.shop.category_id)

    def test_a_view_category_is_rejected(self):
        """Una carpeta no es un comercio: rompería el recuento del directorio.

        `company_qty` cuenta compañías en las categorías normales y en las de
        tipo vista sólo suma las de sus hijas. Un comercio colgado de una
        carpeta no lo cuenta nadie: desaparece del recuento público. El
        dominio del campo ya lo dice, pero un dominio es una pista de
        interfaz, no una comprobación de escritura.
        """
        self.shop.category_id = self.cat_a
        with self.assertRaises(UserError):
            self._as_merchant().set_own_directory_category(self.cat_view.id)
        self.assertEqual(self.shop.category_id, self.cat_a)

    def test_a_user_with_no_shop_gets_nothing_and_writes_nothing(self):
        orphan = new_test_user(
            self.env,
            login="portal-sin-comercio",
            groups="base.group_portal",
            context={"no_reset_password": True, "tracking_disable": True},
        )
        orphan.company_id = self.env.ref("base.main_company")
        env = self.env(user=orphan.id)
        self.assertFalse(env["res.company"]._get_own_company_for_directory())
        with self.assertRaises(AccessError):
            env["res.company"].set_own_directory_category(self.cat_a.id)

    def test_the_platform_company_is_never_somebody_s_shop(self):
        """Un portal enganchado a la compañía de la plataforma no la recategoriza.

        Sin esta guarda, quien tuviera una cuenta portal sobre Canarias
        Conectada podría cambiar la categoría de la propia plataforma: una
        escalada de privilegio con forma de desplegable.
        """
        main = self.env.ref("base.main_company")
        # company_id tiene que estar entre las permitidas o el propio ORM
        # rechaza la asignación antes de llegar a lo que se quiere probar.
        self.merchant.company_ids = [(4, main.id)]
        self.merchant.company_id = main
        env = self.env(user=self.merchant.id)
        self.assertFalse(env["res.company"]._get_own_company_for_directory())

    def test_an_archived_company_is_not_editable(self):
        """Un comercio dado de baja no se recategoriza.

        Este estado el ORM no lo deja construir: no permite archivar una
        compañía que aún es la de un usuario, ni asignar a un usuario una
        compañía archivada. Pero sí se alcanza archivando POR FUERA del ORM
        —un UPDATE masivo, una migración, una limpieza a mano—, que es cuando
        aparecen usuarios apuntando a comercios cerrados.

        Por eso el archivado se hace aquí en SQL: es la única forma de llegar
        a la rama que la guarda protege, y reproduce el único camino real.
        """
        self.env.cr.execute(
            "UPDATE res_company SET active = false WHERE id = %s", (self.shop.id,)
        )
        self.shop.invalidate_recordset(["active"])
        env = self.env(user=self.merchant.id)
        self.assertFalse(env["res.company"]._get_own_company_for_directory())
        with self.assertRaises(AccessError):
            env["res.company"].set_own_directory_category(self.cat_a.id)

    def test_only_the_category_field_is_written(self):
        """La escalada se limita a un campo: el nombre no puede cambiar por aquí."""
        original = self.shop.name
        self._as_merchant().set_own_directory_category(self.cat_a.id)
        self.assertEqual(self.shop.name, original)


@tagged("post_install", "-at_install")
class TestSelfServicePage(HttpCase):
    """La página se pinta de verdad.

    Los tests de arriba prueban la lógica; esto prueba la plantilla, que es
    donde un fallo de QWeb solo aparece al renderizar. No se puede comprobar
    desde el shell: ``website.layout`` necesita una petición HTTP real.
    """

    def setUp(self):
        super().setUp()
        # Pinned to the website's default language: since the seven-language
        # rollout the anonymous negotiation can land on en_US and every
        # unprefixed request becomes a 303 language hop first.
        website = self.env["website"].search([], limit=1)
        self.opener.cookies["frontend_lang"] = website.default_lang_id.code
        self.shop = (
            self.env["res.company"]
            .with_context(no_microsite_auto=True)
            .create({"name": "Comercio de la pagina"})
        )
        self.category = self.env["res.company.category"].create(
            {"name": "Categoria de la pagina"}
        )
        self.merchant = new_test_user(
            self.env,
            login="comerciante-pagina",
            password="comerciante-pagina",
            groups="base.group_portal",
            company_id=self.shop.id,
            company_ids=[(6, 0, [self.shop.id])],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def _csrf_token(self, html):
        """El token real de ESTA sesión, sacado del formulario que lo lleva."""
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
        self.assertTrue(match, "la pagina no trae csrf_token")
        return match.group(1)

    def test_the_page_requires_a_login(self):
        """auth='user': un anonimo no ve el formulario, va al login."""
        response = self.url_open("/mi-comercio", allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("/web/login", response.headers.get("Location", ""))

    def test_the_page_renders_and_saves_for_a_merchant(self):
        self.authenticate("comerciante-pagina", "comerciante-pagina")
        self.assertEqual(self.session.uid, self.merchant.id, "no se pudo abrir sesion")

        response = self.url_open("/mi-comercio")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("Comercio de la pagina", body)
        self.assertIn("/mi-comercio/categoria", body)
        # Sin categoria todavia: el aviso tiene que verse.
        self.assertIn("Sin categor", body)

        response = self.url_open(
            "/mi-comercio/categoria",
            data={
                "category_id": str(self.category.id),
                "csrf_token": self._csrf_token(body),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.shop.invalidate_recordset(["category_id"])
        self.assertEqual(self.shop.category_id, self.category)
        # Y la pagina ya la muestra.
        self.assertIn("Categoria de la pagina", response.text)

    def test_a_post_without_a_valid_csrf_token_changes_nothing(self):
        """Sin token bueno no se escribe: la ruta va con csrf=True por algo.

        La escritura es un POST con sudo detras. Si valiera un POST desde
        fuera, cualquier pagina podria recategorizar el comercio de un
        comerciante con la sesion que el ya tiene abierta. Odoo responde 400
        ("Session expired (invalid CSRF token)") y no llega a la ruta.
        """
        self.authenticate("comerciante-pagina", "comerciante-pagina")
        for label, data in (
            ("sin token", {"category_id": str(self.category.id)}),
            (
                "token falsificado",
                {"category_id": str(self.category.id), "csrf_token": "no-soy-el-token"},
            ),
        ):
            with self.subTest(case=label):
                response = self.url_open("/mi-comercio/categoria", data=data)
                self.assertEqual(response.status_code, 400, label)
                self.shop.invalidate_recordset(["category_id"])
                self.assertFalse(
                    self.shop.category_id,
                    f"{label}: la categoria no debe cambiar",
                )
