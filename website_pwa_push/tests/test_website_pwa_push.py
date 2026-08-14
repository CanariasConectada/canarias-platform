# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged

from odoo.addons.website_pwa.controllers.main import WebsitePWA
from odoo.addons.website_pwa_push.controllers.main import WebsitePWAPush

FRONTEND_ASSET = "website_pwa_push/static/src/js/pwa_push.js"


@tagged("post_install", "-at_install")
class TestWebsitePWAPush(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.website.write({"pwa_enabled": True, "pwa_push_enabled": True})

    def _worker(self):
        res = self.url_open("/service-worker.js")
        self.assertEqual(res.status_code, 200)
        return res.content.decode()

    def _asset_paths(self, bundle):
        """Rutas de un bundle, tal y como las resuelve Odoo al servirlo.

        Cada entrada es una tupla cuyo primer elemento es la ruta web; el resto
        (ruta absoluta, bundle de origen, fecha) cambia entre versiones, así
        que se indexa por posición en lugar de desempaquetar.
        """
        ir_asset = self.env["ir.asset"]
        return [
            asset[0]
            for asset in ir_asset._get_asset_paths(bundle, ir_asset._get_asset_params())
        ]

    # ------------------------------------------------------------------
    # El worker con push activado
    # ------------------------------------------------------------------

    def test_push_handlers_are_appended_when_push_is_enabled(self):
        """Sin estos tres manejadores no hay Web Push en absoluto.

        `push` es lo único que puede pintar la notificación,
        `notificationclick` lo único que la convierte en una visita, y
        `pushsubscriptionchange` lo único que sobrevive a la rotación del
        endpoint: sin él el visitante deja de recibir sin que nada lo explique.
        """
        worker = self._worker()
        self.assertIn('self.addEventListener("push"', worker)
        self.assertIn('self.addEventListener("notificationclick"', worker)
        self.assertIn('self.addEventListener("pushsubscriptionchange"', worker)

    def test_notification_click_opens_the_public_channel_page(self):
        """El clic tiene que llevar a una página que un invitado pueda abrir.

        El worker del backend manda a `/odoo/...`, que a un visitante anónimo
        le responde una pantalla de login. La página pública del canal
        (`/discuss/channel/<id>`, auth="public") es la que sí puede ver.
        """
        worker = self._worker()
        self.assertIn("/discuss/channel/", worker)
        self.assertNotIn("/odoo/", worker)

    def test_resubscription_uses_the_public_registration_route(self):
        """Volver a suscribirse tiene que pasar por la ruta pública.

        La de core (`/web/dataset/call_kw/...register_devices`) es
        `auth="user"`: para el visitante anónimo que justifica todo este stack
        simplemente no existe.
        """
        worker = self._worker()
        self.assertIn("/mail/push/subscribe", worker)
        self.assertNotIn("/web/dataset/call_kw", worker)

    def test_notifications_of_the_same_channel_share_a_tag(self):
        """Una ráfaga de mensajes debe colapsar en un solo aviso.

        Sin `tag`, veinte mensajes seguidos son veinte notificaciones en la
        pantalla de bloqueo, y la primera reacción del visitante es desactivar
        los avisos.
        """
        worker = self._worker()
        self.assertIn("options.tag = tag", worker)
        self.assertIn("cc-push-", worker)

    def test_worker_never_imports_the_backend_push_library(self):
        """`importScripts` en el worker público sería un 404 que lo mata entero.

        El worker de core hace `importScripts("/mail/static/lib/...")`, y un
        import que falla aborta la instalación del service worker completo,
        llevándose por delante también la caché offline de website_pwa.
        """
        worker = self._worker()
        self.assertNotIn("importScripts", worker)

    def test_route_still_serves_exactly_what_the_hook_returns(self):
        """La ruta sigue sirviendo el hook literal, ya con nuestro añadido.

        Es la garantía que website_pwa fija para sus extensiones; si se rompe,
        lo que se prueba aquí no es lo que llega al teléfono.
        """
        expected = WebsitePWAPush()._pwa_service_worker_content(self.website)
        res = self.url_open("/service-worker.js")
        self.assertEqual(res.content, expected.encode())

    def test_root_scope_header_survives_the_extension(self):
        """Sin `Service-Worker-Allowed: /` el worker no controla nada.

        Extender el cuerpo no puede costar la cabecera: el worker seguiría
        instalándose, pero con el alcance recortado al directorio desde el que
        se sirve.
        """
        res = self.url_open("/service-worker.js")
        self.assertEqual(res.headers.get("Service-Worker-Allowed"), "/")
        self.assertIn("javascript", res.headers["Content-Type"])

    # ------------------------------------------------------------------
    # El worker con push desactivado: la regresión que de verdad importa
    # ------------------------------------------------------------------

    def test_worker_is_byte_identical_to_website_pwa_when_push_is_off(self):
        """Un sitio sin push tiene que recibir EXACTAMENTE los bytes de antes.

        El worker está cacheado en teléfonos reales: el navegador compara byte
        a byte el fichero que ya tiene con el que sirve el servidor, y
        cualquier diferencia -- aunque sea un comentario o una rama muerta --
        instala una versión nueva en cada visitante de los 218 sitios que no
        han pedido push.
        """
        self.website.pwa_push_enabled = False
        base = WebsitePWA._pwa_service_worker_content(WebsitePWAPush(), self.website)
        res = self.url_open("/service-worker.js")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, base.encode())

    def test_worker_does_not_grow_when_push_is_off(self):
        """Dicho como tamaño, que es como se paga en un móvil con datos."""
        with_push = len(self._worker())
        self.website.pwa_push_enabled = False
        without_push = len(self._worker())
        self.assertLess(without_push, with_push)
        base = WebsitePWA._pwa_service_worker_content(WebsitePWAPush(), self.website)
        self.assertEqual(without_push, len(base))

    def test_push_alone_does_not_resurrect_a_disabled_app(self):
        """Con la app apagada no hay worker, ni siquiera con push encendido.

        Los manejadores viven DENTRO del service worker, así que un sitio con
        `pwa_push_enabled` y `pwa_enabled` a False tiene que seguir dando 404:
        el módulo no puede convertirse en una puerta trasera que reactive la
        app en un sitio que la apagó.
        """
        self.website.pwa_enabled = False
        self.assertEqual(self.url_open("/service-worker.js").status_code, 404)

    # ------------------------------------------------------------------
    # La página
    # ------------------------------------------------------------------

    def test_layout_marks_the_page_only_when_push_is_enabled(self):
        """La marca es lo único que distingue "hay push aquí" en el navegador.

        El enlace al manifiesto solo dice que la app está activa. Sin esta
        etiqueta el botón aparecería en sitios cuyo worker no tiene
        manejadores, y un visitante que aceptara quedaría suscrito a
        notificaciones que nunca se pintan.
        """
        self.assertIn('name="cc-pwa-push"', self.url_open("/").text)
        self.website.pwa_push_enabled = False
        self.assertNotIn('name="cc-pwa-push"', self.url_open("/").text)

    def test_frontend_asset_is_in_the_frontend_bundle_only(self):
        """El botón es del sitio público; en el backend no pinta nada.

        Cargarlo también en `web.assets_backend` sería peso en cada arranque
        del ERP para un `#wrapwrap` que allí no existe.
        """
        frontend = self._asset_paths("web.assets_frontend")
        backend = self._asset_paths("web.assets_backend")
        self.assertTrue(
            any(path.endswith(FRONTEND_ASSET) for path in frontend),
            "pwa_push.js no está en web.assets_frontend",
        )
        self.assertFalse(
            any(path.endswith(FRONTEND_ASSET) for path in backend),
            "pwa_push.js no debería estar en web.assets_backend",
        )
