# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.mail.tools.jwt import InvalidVapidError
from odoo.addons.mail_push_guest.models.mail_push_device import MAX_DEVICES_PER_PERSONA

from .common import (
    BROWSER_KEYS,
    FCM_ENDPOINT,
    MOZILLA_ENDPOINT,
    VAPID_PUBLIC_KEY_PARAM,
    MailPushGuestMixin,
)


@tagged("post_install", "-at_install")
class TestPushDevicePersona(MailPushGuestMixin, TransactionCase):
    """El dueño de un dispositivo es UNA persona: o socio, o visitante."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_push_fixtures()

    def test_guest_device_has_no_partner(self):
        """Un dispositivo de visitante existe SIN socio.

        Es la razón de ser del módulo: en core `partner_id` es `required=True`
        con `default=self.env.user.partner_id`
        (mail/models/mail_push_device.py:17-19), así que este `create` era
        imposible -- o peor, silenciosamente atribuido al socio público.
        """
        device = self._create_device(FCM_ENDPOINT % "guest-b", guest=self.guest_b)
        self.assertEqual(device.guest_id, self.guest_b)
        self.assertFalse(device.partner_id)
        self.assertEqual(json.loads(device.keys), BROWSER_KEYS)

    def test_create_with_guest_ignores_partner_default(self):
        """Dar un visitante NEUTRALIZA el default de socio de core.

        Los defaults se mezclan en `vals` dentro de `create`
        (odoo/orm/models.py:4791-4793), antes de cualquier otra cosa. Sin la
        sobrescritura de `create`, este mismo `create` habría acabado con el
        socio del usuario actual además del visitante, y habría reventado
        contra el CHECK con un IntegrityError ilegible.
        """
        device = (
            self.env["mail.push.device"]
            .sudo()
            .create(
                {
                    "endpoint": FCM_ENDPOINT % "default-check",
                    "keys": json.dumps(BROWSER_KEYS),
                    "guest_id": self.guest_b.id,
                }
            )
        )
        self.assertFalse(device.partner_id)

    @mute_logger("odoo.sql_db")
    def test_constraint_rejects_both_personas(self):
        """Las dos personas a la vez las rechaza el CHECK de SQL.

        El CHECK dispara en el INSERT, ANTES de que el ORM valide nada, y por
        eso es la capa que de verdad impide la fila de dos dueños: también la
        de un módulo que escriba por SQL crudo.
        """
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["mail.push.device"].sudo().create(
                {
                    "endpoint": FCM_ENDPOINT % "both",
                    "keys": json.dumps(BROWSER_KEYS),
                    "partner_id": self.partner_author.id,
                    "guest_id": self.guest_b.id,
                }
            )

    def test_constraint_rejects_no_persona_on_create(self):
        """Sin ninguna persona tampoco vale: lo caza el `@api.constrains`.

        Ningún CHECK de SQL expresa aquí el "ninguno" (ver el comentario del
        modelo), así que esta es la capa que da el mensaje legible en una ruta
        que atiende a anónimos.
        """
        with self.assertRaises(ValidationError):
            self.env["mail.push.device"].sudo().create(
                {
                    "endpoint": FCM_ENDPOINT % "orphan",
                    "keys": json.dumps(BROWSER_KEYS),
                    "partner_id": False,
                }
            )

    def test_constraint_rejects_no_persona_on_write(self):
        """Vaciar la persona de una fila existente es el mismo agujero."""
        device = self._create_device(FCM_ENDPOINT % "guest-write", guest=self.guest_b)
        with self.assertRaises(ValidationError):
            device.write({"guest_id": False})

    def test_binding_partner_releases_guest(self):
        """Atar un socio SUELTA al visitante en la misma escritura.

        Es lo que le pasa a un navegador que se suscribe como visitante y
        luego inicia sesión: el cliente web llama a `register_devices`, que
        busca por endpoint y escribe `partner_id`
        (mail/models/mail_push_device.py:58-66) sin saber que `guest_id`
        existe. Sin este comportamiento, código de core -- intocable --
        reventaría contra el CHECK.
        """
        device = self._create_device(FCM_ENDPOINT % "login", guest=self.guest_b)
        device.write({"partner_id": self.partner_author.id})
        self.assertEqual(device.partner_id, self.partner_author)
        self.assertFalse(device.guest_id)

    def test_guest_unlink_cascades_devices(self):
        """Al borrar el visitante desaparece su dispositivo.

        `ondelete="cascade"` explícito: una suscripción sin dueño seguiría
        siendo un endpoint al que este servidor hace POST.
        """
        device = self._create_device(
            FCM_ENDPOINT % "cascade-guest", guest=self.guest_outsider
        )
        self.guest_outsider.unlink()
        self.assertFalse(device.exists())

    def test_partner_unlink_cascades_devices(self):
        """Lo mismo por el lado del socio, y NO por accidente.

        El `ondelete` por defecto de un m2o se deduce de `required`
        (odoo/orm/fields_relational.py:270-282): al relajar el `required=True`
        de core, este FK habría pasado de `restrict` a `set null` en silencio,
        y `set null` es la única política que este modelo no sobrevive --
        dejaría filas sin persona por detrás del ORM, violando la restricción
        que el propio módulo declara.
        """
        partner = self.env["res.partner"].create({"name": "Throwaway"})
        device = self._create_device(FCM_ENDPOINT % "cascade-partner", partner=partner)
        partner.unlink()
        self.assertFalse(device.exists())

    def test_register_returns_empty_when_the_endpoint_is_not_the_caller_s(self):
        """El contrato del que depende el silencio de la ruta.

        `_register_for_persona` devuelve el recordset VACÍO cuando se niega a
        reapuntar una fila ajena, y la ruta traduce eso al mismo `True` que un
        registro correcto. Si un día alguien hiciera que en vez de eso lanzara
        una excepción, la ruta pasaría a confirmar que ese endpoint existe a
        quien lo tenga sin deberlo tener. Se fija aquí, en el modelo, porque es
        donde se decide.
        """
        endpoint = FCM_ENDPOINT % "contract-foreign"
        self._create_device(endpoint, guest=self.guest_b)
        result = self.env["mail.push.device"]._register_for_persona(
            guest=self.guest_outsider,
            endpoint=endpoint,
            keys=dict(BROWSER_KEYS),
            vapid_public_key=self.vapid_public_key,
        )
        self.assertFalse(result)
        self.assertEqual(result._name, "mail.push.device")
        device = (
            self.env["mail.push.device"].sudo().search([("endpoint", "=", endpoint)])
        )
        self.assertEqual(device.guest_id, self.guest_b)

    def test_register_refuses_when_the_database_has_no_vapid_key(self):
        """Sin par VAPID en la base, NADIE registra. Ni siquiera un anónimo.

        `_verify_vapid_public_key` (mail/models/mail_push_device.py:86-89) es un
        `==` pelado contra el parámetro. Cuando el par nunca se generó,
        `get_param` devuelve False, así que un cliente que mande `False` (o
        `None`) hace que core compare `False == False` y diga "válida". Detrás
        de `auth="user"` esa forma no se alcanza en la práctica; aquí es el
        estado POR DEFECTO de una base recién creada, y quien llama es
        cualquiera: sin la comprobación de vacío, un anónimo llena la tabla de
        dispositivos para los que nunca se podrá cifrar nada.

        Se prueban los dos valores que de verdad se cuelan. Los demás
        (`""`, un dict, un número) ya los rechaza el `==` de core, así que no
        demostrarían nada sobre esta comprobación.
        """
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", VAPID_PUBLIC_KEY_PARAM)]
        ).unlink()

        for vapid_public_key in (None, False):
            with self.subTest(vapid_public_key=vapid_public_key):
                endpoint = FCM_ENDPOINT % ("no-vapid-%s" % vapid_public_key)
                with self.assertRaises(InvalidVapidError):
                    self.env["mail.push.device"]._register_for_persona(
                        guest=self.guest_b,
                        endpoint=endpoint,
                        keys=dict(BROWSER_KEYS),
                        vapid_public_key=vapid_public_key,
                    )
                self.assertFalse(
                    self.env["mail.push.device"]
                    .sudo()
                    .search([("endpoint", "=", endpoint)]),
                    "Se registró un dispositivo que nada podrá cifrar",
                )

    def test_the_orm_door_cannot_wipe_every_device_asking_for_the_key(self):
        """LA TRAMPA DE CORE, por la otra puerta.

        `get_web_push_vapid_public_key()` regenera el par cuando falta el
        parámetro, y empieza borrando TODOS los dispositivos de la base
        (mail/models/mail_push_device.py:33-45). El módulo ya cerró eso en
        `/mail/push/vapid`; el método sigue siendo alcanzable por
        `/web/dataset/call_kw`, que no comprueba ACL de modelo, así que una
        cuenta de portal podía borrar todas las suscripciones de la plataforma
        y rotar el par -- invalidando las que cada navegador guarda -- sólo
        pidiendo la clave pública.

        Requiere que la clave esté ausente (base nueva, o justo después de que
        un administrador la borre), que es exactamente lo que hace esta prueba.
        """
        device = self._create_device(
            FCM_ENDPOINT % "vapid-survivor", guest=self.guest_b
        )
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", VAPID_PUBLIC_KEY_PARAM)]
        ).unlink()

        result = (
            self.env["mail.push.device"]
            .with_user(self.portal_user)
            .get_web_push_vapid_public_key()
        )

        self.assertFalse(result, "Se le generó un par a una cuenta de portal")
        self.assertTrue(device.exists(), "Le borraron los dispositivos a todo el mundo")
        self.assertFalse(
            self.env["ir.config_parameter"].sudo().get_param(VAPID_PUBLIC_KEY_PARAM),
            "La rotación de claves no es de quien llama",
        )

    def test_an_administrator_still_generates_the_vapid_pair(self):
        """CONTROL POSITIVO: el arranque de una base nueva sigue funcionando.

        No hay acción de Ajustes que genere el par: este método es el ÚNICO
        generador que trae `mail`, y lo dispara el propio cliente web la
        primera vez que un administrador activa las notificaciones. Si la
        precondición valiera para todo el mundo, una base nueva se quedaría sin
        push para siempre.

        Se llama COMO UN USUARIO de verdad, no con el entorno de la prueba: ese
        es superusuario (`env.su`), y pasaría por la otra rama de la
        precondición sin ejercitar el `has_group`.
        """
        admin = self.env.ref("base.user_admin")
        self.assertTrue(
            admin.has_group("base.group_system"),
            "El fixture de administrador ya no tiene Ajustes",
        )
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", VAPID_PUBLIC_KEY_PARAM)]
        ).unlink()

        result = (
            self.env["mail.push.device"]
            .with_user(admin)
            .get_web_push_vapid_public_key()
        )

        self.assertTrue(result)
        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param(VAPID_PUBLIC_KEY_PARAM),
            result,
        )

    def test_reading_an_existing_vapid_key_is_open_to_everybody(self):
        """Leer la clave pública no se ha restringido: es pública por diseño.

        Se le manda a cada navegador que se suscribe. Lo que se cerró es la
        GENERACIÓN, que es la rama destructiva.
        """
        self.assertEqual(
            self.env["mail.push.device"]
            .with_user(self.portal_user)
            .get_web_push_vapid_public_key(),
            self.vapid_public_key,
        )

    def test_core_partner_registration_still_works(self):
        """REGRESIÓN DE CORE: `register_devices` sigue registrando.

        El camino feliz de un usuario identificado: no hay fila previa, se
        crea, y queda atada a SU socio.
        """
        core_endpoint = FCM_ENDPOINT % "core-happy-path"
        self.env["mail.push.device"].with_user(self.user_author).register_devices(
            endpoint=core_endpoint,
            keys=BROWSER_KEYS,
            vapid_public_key=self.vapid_public_key,
            expirationTime=None,
        )
        device = (
            self.env["mail.push.device"]
            .sudo()
            .search([("endpoint", "=", core_endpoint)])
        )
        self.assertEqual(len(device), 1)
        self.assertEqual(device.partner_id, self.partner_author)
        self.assertFalse(device.guest_id)

    def test_core_registration_refuses_an_endpoint_that_is_not_a_push_service(self):
        """La lista blanca YA NO es sólo de la ruta pública.

        Antes valía el argumento "detrás de `auth="user"` lo paga core". No lo
        vale: `/web/dataset/call_kw` no comprueba ACL de modelo y en esta
        plataforma una cuenta identificada es cualquiera que se haya
        registrado. Sin esta comprobación, un usuario de portal registraba
        `https://<host interno>/...` y el worker lo consultaba en cada mensaje,
        con el cuerpo de la respuesta acabando en el log
        (mail/tools/web_push.py:143-189).

        Se prueban las tres formas que llegaron por esta puerta en la
        validación: el host interno a pelo, `http://` sin TLS y el disfraz de
        userinfo (`https://fcm.googleapis.com@<host interno>/`), que se lee como
        un host permitido y resuelve a otro.
        """
        for endpoint in (
            "https://169.254.169.254/latest/meta-data/iam/security-credentials/",
            "http://fcm.googleapis.com/fcm/send/plain-http",
            "https://fcm.googleapis.com@169.254.169.254/x",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValidationError):
                    self._register_as(self.portal_user, endpoint=endpoint)
                self.assertFalse(
                    self.env["mail.push.device"]
                    .sudo()
                    .search([("endpoint", "=", endpoint)]),
                    "Se guardó la fila igualmente",
                )

    def test_core_registration_enforces_the_device_cap(self):
        """El tope de dispositivos tampoco es sólo de la ruta pública.

        Core crea sin contar, así que un tope que sólo mirara `/mail/push/
        subscribe` sería un tope que se rodea llamando al método de al lado.
        Se comprueba además que la fila número seis NO se guarda y que
        refrescar una de las cinco ya existentes sigue pasando: el tope guarda
        la creación, no el re-registro.
        """
        for index in range(MAX_DEVICES_PER_PERSONA):
            self._create_device(
                FCM_ENDPOINT % ("cap-orm-%s" % index), partner=self.partner_author
            )

        with self.assertRaises(ValidationError):
            self._register_as(
                self.user_author, endpoint=FCM_ENDPOINT % "cap-orm-one-too-many"
            )

        devices = self.env["mail.push.device"].sudo()
        self.assertEqual(
            devices.search_count([("partner_id", "=", self.partner_author.id)]),
            MAX_DEVICES_PER_PERSONA,
        )
        # El re-registro de una fila propia no cuenta como alta.
        self._register_as(self.user_author, endpoint=FCM_ENDPOINT % "cap-orm-0")
        self.assertEqual(
            devices.search_count([("partner_id", "=", self.partner_author.id)]),
            MAX_DEVICES_PER_PERSONA,
        )

    # ------------------------------------------------------------------
    # `register_devices`: la MISMA regla de propiedad por la puerta del ORM
    #
    # `/web/dataset/call_kw` no comprueba ACL de modelo (`call_kw` sólo
    # rechaza métodos privados) y `register_devices` hace sudo por dentro, así
    # que la concesión a `base.group_system` no frena a nadie: cualquier cuenta
    # identificada llega. Con auto-registro abierto, "cuenta identificada" es
    # cualquiera. Una regla de propiedad que valiera en la ruta pública y no
    # aquí no sería una regla de propiedad.
    # ------------------------------------------------------------------

    def _register_as(self, user, **kw):
        """Llama a `register_devices` como lo haría el cliente web de core."""
        payload = {
            "keys": dict(BROWSER_KEYS),
            "vapid_public_key": self.vapid_public_key,
            "expirationTime": None,
        }
        payload.update(kw)
        return self.env["mail.push.device"].with_user(user).register_devices(**payload)

    def test_core_registration_cannot_take_over_a_guest_endpoint(self):
        """Una cuenta de portal no se queda con el endpoint de un visitante."""
        endpoint = FCM_ENDPOINT % "orm-takeover-guest"
        self._create_device(endpoint, guest=self.guest_b)

        self._register_as(self.portal_user, endpoint=endpoint)

        device = (
            self.env["mail.push.device"].sudo().search([("endpoint", "=", endpoint)])
        )
        self.assertEqual(len(device), 1)
        self.assertEqual(device.guest_id, self.guest_b)
        self.assertFalse(device.partner_id)

    def test_core_registration_cannot_take_over_another_partner_endpoint(self):
        """Y tampoco con el de otra cuenta.

        Es el mismo agujero que core lleva de serie: detrás de `auth="user"`
        lo da por bueno, pero un usuario de portal es un usuario.
        """
        endpoint = FCM_ENDPOINT % "orm-takeover-partner"
        self._create_device(endpoint, partner=self.partner_author)

        self._register_as(self.portal_user, endpoint=endpoint)

        device = (
            self.env["mail.push.device"].sudo().search([("endpoint", "=", endpoint)])
        )
        self.assertEqual(device.partner_id, self.partner_author)

    def test_core_registration_cannot_walk_a_foreign_row_with_previous_endpoint(self):
        """`previousEndpoint` es el vector afilado, y va por el mismo sitio.

        Core busca la fila por `previousEndpoint` cuando se le da y le
        reescribe el endpoint (mail/models/mail_push_device.py:57-66). Su uso
        legítimo es `pushsubscriptionchange`, donde el navegador renombra SU
        suscripción. El ilegítimo es pasar el endpoint de la víctima como
        anterior y el propio como nuevo: la fila ajena acaba apuntando a donde
        diga el atacante. Por eso lo que se comprueba es la clave de BÚSQUEDA,
        no el endpoint nuevo.
        """
        victim_endpoint = FCM_ENDPOINT % "orm-walk-victim"
        attacker_endpoint = FCM_ENDPOINT % "orm-walk-attacker"
        self._create_device(victim_endpoint, guest=self.guest_b)

        self._register_as(
            self.portal_user,
            endpoint=attacker_endpoint,
            previousEndpoint=victim_endpoint,
        )

        devices = self.env["mail.push.device"].sudo()
        victim = devices.search([("endpoint", "=", victim_endpoint)])
        self.assertEqual(victim.guest_id, self.guest_b, "Le movieron la fila")
        self.assertFalse(
            devices.search([("endpoint", "=", attacker_endpoint)]),
            "El atacante acabó con la fila de la víctima en su endpoint",
        )

    # ------------------------------------------------------------------
    # CONTROLES POSITIVOS: lo propio no se bloquea
    #
    # Las dos pruebas que siguen dicen lo que core hace DE VERDAD con la fila
    # de quien llama, que no es lo que su nombre sugiere. Core sólo escribe
    # cuando la fila es de OTRO:
    #
    #     if mail_push_device.partner_id != self.env.user.partner_id:
    #         mail_push_device.write({...})
    #                          (mail/models/mail_push_device.py:59-66)
    #
    # Es decir: refrescar tu propia expiración y renombrar tu propio endpoint
    # con `previousEndpoint` son caminos MUERTOS en Odoo 19 de fábrica, con
    # este módulo y sin él (comprobado contra una base de control sin él). Lo
    # que estas pruebas fijan, entonces, es la única mitad que sí depende de
    # nosotros: que la comprobación de propiedad DEJA PASAR la fila propia, y
    # que la llamada no rompe nada ni duplica filas. Por eso cada una empieza
    # afirmando `_may_claim_device`: si un día se rompiera nuestra capa, la
    # prueba señalaría a nuestra capa y no al no-op de core.
    #
    # Si core llega a arreglar ese `!=`, estas dos pruebas fallarán con un
    # mensaje que dice exactamente qué cambió, que es lo que se quiere.
    # ------------------------------------------------------------------

    def test_core_registration_lets_the_caller_claim_its_own_device(self):
        """La fila propia se puede reclamar; core, aun así, no la refresca.

        El caso normal del navegador que re-suscribe. Nuestra comprobación lo
        autoriza (primera aserción); core después no escribe nada, porque su
        condición es "la fila es de otro". La expiración enviada se pierde: es
        el no-op de core, no un rechazo nuestro.
        """
        endpoint = FCM_ENDPOINT % "orm-own-refresh"
        device = self._create_device(endpoint, partner=self.partner_author)

        self.assertTrue(
            self.env["mail.push.device"]._may_claim_device(
                device, partner=self.partner_author
            ),
            "La comprobación de propiedad bloquea al dueño de la fila",
        )

        self._register_as(
            self.user_author,
            endpoint=endpoint,
            expirationTime="2099-01-01 00:00:00",
        )

        device.invalidate_recordset()
        self.assertTrue(device.exists(), "La fila propia desapareció")
        self.assertEqual(device.partner_id, self.partner_author)
        self.assertFalse(
            device.expiration_time,
            "core ha empezado a refrescar la fila propia: revisar "
            "mail/models/mail_push_device.py:59 y actualizar el ROADMAP",
        )
        self.assertEqual(
            len(
                self.env["mail.push.device"]
                .sudo()
                .search([("endpoint", "=", endpoint)])
            ),
            1,
            "Se duplicó la fila en vez de dejarla como estaba",
        )

    def test_core_registration_does_not_rename_the_caller_own_endpoint(self):
        """`pushsubscriptionchange`: el renombrado tampoco ocurre.

        El navegador cambia de endpoint solo y avisa con el anterior. La fila
        es suya -- y justo por eso core se la salta. No se renombra y tampoco
        se crea una segunda: core busca por `previousEndpoint`, encuentra, y no
        hace nada. El resultado es la fila vieja intacta, con un endpoint que
        el navegador ya no tiene, hasta que el servicio de push conteste
        404/410 y core la borre (mail/models/mail_thread.py:3933-3942).
        """
        old_endpoint = FCM_ENDPOINT % "orm-rename-old"
        new_endpoint = FCM_ENDPOINT % "orm-rename-new"
        device = self._create_device(old_endpoint, partner=self.partner_author)

        self.assertTrue(
            self.env["mail.push.device"]._may_claim_device(
                device, partner=self.partner_author
            ),
            "La comprobación de propiedad bloquea al dueño de la fila",
        )

        self._register_as(
            self.user_author,
            endpoint=new_endpoint,
            previousEndpoint=old_endpoint,
        )

        device.invalidate_recordset()
        self.assertEqual(
            device.endpoint,
            old_endpoint,
            "core ha empezado a renombrar la fila propia: revisar "
            "mail/models/mail_push_device.py:59 y actualizar el ROADMAP",
        )
        self.assertEqual(device.partner_id, self.partner_author)
        self.assertFalse(
            self.env["mail.push.device"]
            .sudo()
            .search([("endpoint", "=", new_endpoint)]),
            "Apareció una segunda fila con el endpoint nuevo",
        )

    def test_core_registration_still_raises_on_a_stale_vapid_key(self):
        """La clave VAPID se sigue comprobando ANTES que la propiedad.

        Fija el orden a posta. Si la comprobación de propiedad fuera primero,
        un cliente con un par caducado apuntando a un endpoint ajeno recibiría
        silencio en vez de `InvalidVapidError` -- y la prueba de core
        `test_push_notification_regenerate_vapid_keys`, que hace exactamente
        eso contra un dispositivo de otro usuario, se rompería.
        """
        endpoint = FCM_ENDPOINT % "orm-stale-vapid"
        self._create_device(endpoint, guest=self.guest_b)
        with self.assertRaises(InvalidVapidError):
            self._register_as(
                self.portal_user,
                endpoint=endpoint,
                vapid_public_key="not-the-key",
            )

    def test_core_unregistration_cannot_silence_another_persona(self):
        """El oráculo de borrado tampoco queda abierto por la puerta del ORM.

        Es el mismo agujero que el módulo ya cerró en
        `/mail/push/unsubscribe`, en el mismo modelo y por la misma ruta.
        Arreglar sólo el registro habría movido el hueco, no cerrado.
        """
        endpoint = FCM_ENDPOINT % "orm-silence"
        device = self._create_device(endpoint, guest=self.guest_b)

        self.env["mail.push.device"].with_user(self.portal_user).unregister_devices(
            endpoint=endpoint
        )

        self.assertTrue(device.exists(), "Le borraron la suscripción a otro")

    def test_core_unregistration_removes_the_caller_own_device(self):
        """CONTROL POSITIVO: darse de baja de lo propio sigue funcionando."""
        endpoint = FCM_ENDPOINT % "orm-own-unsub"
        device = self._create_device(endpoint, partner=self.partner_author)

        self.env["mail.push.device"].with_user(self.user_author).unregister_devices(
            endpoint=endpoint
        )

        self.assertFalse(device.exists())

    def test_core_partner_lookup_ignores_guest_devices(self):
        """La búsqueda por socio de core no ve los dispositivos de visitante.

        `_web_push_get_partners_parameters` filtra por `partner_id`
        (mail/models/mail_thread.py:3897-3909). Al hacer opcional ese campo
        había que comprobar que un `partner_id` NULL no se cuela en ese
        `search`, porque entonces core enviaría a visitantes por un camino que
        luego derefencia `device.partner_id.lang`.
        """
        partner_device = self._create_device(
            FCM_ENDPOINT % "lookup-partner", partner=self.partner_author
        )
        self._create_device(MOZILLA_ENDPOINT % "lookup-guest", guest=self.guest_b)
        devices, private_key, public_key = (
            self.channel._web_push_get_partners_parameters(self.partner_author.ids)
        )
        self.assertEqual(devices, partner_device)
        self.assertEqual(public_key, self.vapid_public_key)
        self.assertTrue(private_key)
