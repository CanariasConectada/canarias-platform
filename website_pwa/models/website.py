# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io
import logging

from PIL import WebPImagePlugin  # noqa: F401  (registers the WebP decoder)
from PIL import Image

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Sizes a browser needs to accept a manifest as installable. 192 is the
# minimum Chrome checks for; 512 is what it uses for the splash screen.
ICON_SIZES = (192, 512)

# Fallback palette when the merchant has not chosen one. Deliberately the
# platform's own colours rather than Odoo's purple, so an unconfigured
# microsite still looks like Canarias Conectada and not like an ERP.
DEFAULT_THEME_COLOR = "#1a7f5a"
DEFAULT_BACKGROUND_COLOR = "#ffffff"

# A home-screen label longer than this is truncated by both Android and iOS,
# so it is cut here where the result can at least be read.
SHORT_NAME_MAX = 12


class Website(models.Model):
    _inherit = "website"

    pwa_enabled = fields.Boolean(
        string="Instalable como app",
        help="When enabled, visitors can install this website on their phone "
        "as an app. Each website is independent: turning it on for one "
        "merchant does not affect any other.",
    )
    pwa_name = fields.Char(
        string="Nombre de la app",
        help="Shown while installing. Defaults to the website name.",
    )
    pwa_short_name = fields.Char(
        string="Nombre corto",
        help="Shown under the icon on the home screen. Keep it short: phones "
        "truncate anything longer than about 12 characters.",
    )
    pwa_theme_color = fields.Char(
        string="Color del tema",
        default=DEFAULT_THEME_COLOR,
        help="Colour of the phone's status bar while the app is open.",
    )
    pwa_background_color = fields.Char(
        string="Color de fondo",
        default=DEFAULT_BACKGROUND_COLOR,
        help="Background of the splash screen shown while the app loads.",
    )
    pwa_icon = fields.Image(
        string="Icono de la app",
        max_width=512,
        max_height=512,
        help="Square image, at least 512x512. Falls back to the website logo.",
    )

    def _pwa_display_name(self):
        """Name shown by the installer."""
        self.ensure_one()
        return self.pwa_name or self.name or self.company_id.name or ""

    def _pwa_short_name(self):
        """Label shown under the home-screen icon.

        Derived on a word boundary rather than a hard slice: cutting "Zona
        Comercial Guanarteme" at twelve characters gives "Zona Comerci",
        which is what the visitor then reads under the icon forever. Falling
        back to the first word or two keeps it a word.
        """
        self.ensure_one()
        if self.pwa_short_name:
            return self.pwa_short_name
        full = self._pwa_display_name()
        if len(full) <= SHORT_NAME_MAX:
            return full
        short = ""
        for word in full.split():
            candidate = f"{short} {word}".strip()
            if short and len(candidate) > SHORT_NAME_MAX:
                break
            short = candidate
        # A single word longer than the limit still has to be cut somewhere.
        return short[:SHORT_NAME_MAX] if short else full[:SHORT_NAME_MAX]

    def _pwa_icon_base64(self):
        """Base64 of the source image, or False when there is none.

        The dedicated ``pwa_icon`` wins when set; otherwise the website logo
        is used, so a merchant who never opens these settings still gets a
        recognisable app instead of a blank square.

        The two fields do not agree on their representation: ``pwa_icon`` is a
        plain stored Image and reads back base64, while ``logo`` is related
        through the company to the partner image and reads back *raw* bytes.
        Feeding the raw ones straight to ``image_process`` fails with "cannot
        decode this file as an image", which is what left the manifest icons
        404 the first time round. The magic number tells the two apart.
        """
        self.ensure_one()
        website = self.sudo()
        source = website.pwa_icon or website.logo
        if not source:
            return False
        if isinstance(source, str):
            source = source.encode()
        # PNG, JPEG and GIF signatures: their presence means the value is the
        # image itself rather than its base64 encoding.
        if source[:4] in (b"\x89PNG", b"GIF8") or source[:3] == b"\xff\xd8\xff":
            return base64.b64encode(source)
        return source

    @api.model
    def _pwa_current(self):
        """Current website, or an empty recordset when PWA is off for it.

        Every entry point (manifest, service worker, icon, layout hook) asks
        this one question, so "is the app enabled here?" is decided in a
        single place.
        """
        website = self.get_current_website()
        return website if website.pwa_enabled else self.browse()

    def _pwa_icon_png(self, size):
        """Square PNG of ``size`` pixels, or False when there is no usable
        source image.

        Deliberately not delegating to ``tools.image.image_process``: the
        merchant logos on this platform are mostly **WebP**, and inside an
        Odoo worker Pillow could not read them — ``Image.open`` answered
        ``UnidentifiedImageError`` on a perfectly valid 344x344 file, so every
        manifest icon 404ed and the browser refused to offer the install
        prompt at all. Pillow discovers its format plugins by scanning, and
        that scan does not find the WebP one here; importing
        ``WebPImagePlugin`` at module level is what registers the decoder.
        ``Image.init()`` alone is not enough — it was tried first.
        """
        self.ensure_one()
        source = self._pwa_icon_base64()
        if not source:
            return False
        Image.init()
        try:
            image = Image.open(io.BytesIO(base64.b64decode(source)))
            image.load()
        except Exception:
            _logger.warning(
                "PWA: no se pudo leer el icono del sitio %s (id %s); "
                "el manifiesto se sirve sin iconos",
                self.name,
                self.id,
            )
            return False

        # Transparent logos must keep their alpha, so RGBA rather than RGB.
        image = image.convert("RGBA")
        # Cover-crop to a square: padding would leave bars inside the rounded
        # mask Android applies, and stretching would distort the brand.
        short_side = min(image.size)
        left = (image.width - short_side) // 2
        top = (image.height - short_side) // 2
        image = image.crop((left, top, left + short_side, top + short_side))
        image = image.resize((size, size), Image.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    def _pwa_manifest_values(self):
        """The manifest, as a plain dict ready to be serialised."""
        self.ensure_one()
        base = self.get_base_url()
        return {
            "name": self._pwa_display_name(),
            "short_name": self._pwa_short_name(),
            # Scope and start_url are the whole point of this module: the
            # backend manifest scopes to /odoo, which is why installing it
            # opened the ERP.
            "scope": "/",
            "start_url": "/",
            "display": "standalone",
            "orientation": "portrait",
            "theme_color": self.pwa_theme_color or DEFAULT_THEME_COLOR,
            "background_color": self.pwa_background_color or DEFAULT_BACKGROUND_COLOR,
            "lang": (self.default_lang_id.code or "es_ES").replace("_", "-"),
            "icons": [
                {
                    "src": f"{base}/website_pwa/icon/{size}.png",
                    "sizes": f"{size}x{size}",
                    "type": "image/png",
                    # "any maskable" lets Android crop the icon into whatever
                    # shape the launcher uses without adding its own frame.
                    "purpose": "any maskable",
                }
                for size in ICON_SIZES
            ],
        }
