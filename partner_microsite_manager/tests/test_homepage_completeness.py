# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import BaseCase

from ..tools.homepage_completeness import classify_url, read_static_homepage

# The importer's homepage, trimmed: background images on the sections,
# texts in SEC1 / Separador headings and the Acerca collapse cards.
STATIC_ARCH = """<t name="Home" t-name="website.homepage_{slug}">
<div id="wrap" class="oe_structure">
<section data-name="Hero" style="background-image: url('{hero}'); background-size: cover"><h1>Shop</h1></section>
<section data-name="SEC1" style="background-image: url({intro})"><div class="container"><h2>{intro_title}</h2></div></section>
<section data-name="Acerca"><div class="row">
<div class="col-lg-6" data-name="Column"><h6>Nuestros servicios</h6>
<div id="acerca2_{slug}" class="collapse"><div class="card card-body bg-light">{services}</div></div></div>
<div class="col-lg-6" data-name="Column"><h6>Sobre nosotros</h6>
<div id="acerca1_{slug}" class="collapse"><div class="card card-body bg-light">{about}</div></div></div>
</div></section>
<section data-name="Separador" style="background-image: url(&quot;{strip}&quot;)"><h2>{strip_title}</h2></section>
</div>
</t>"""


class TestHomepageCompleteness(BaseCase):
    def test_read_static_homepage(self):
        arch = STATIC_ARCH.format(
            slug="x",
            hero="/web/content/42?download=1",
            intro="",
            strip="/web/image/res.company/7/microsite_banner_image",
            intro_title="Intro <b>bold</b>",
            about="About",
            services="Services",
            strip_title="Strip",
        )
        shown = read_static_homepage(arch)
        self.assertEqual(shown["images"]["hero"], ("attachment", 42))
        self.assertEqual(shown["images"]["intro"], ("none", None))
        self.assertEqual(
            shown["images"]["strip"], ("company", (7, "microsite_banner_image"))
        )
        self.assertEqual(shown["intro_title"], "Intro bold")
        # Slots come from the collapse ids, not from the column order.
        self.assertEqual((shown["about"], shown["services"]), ("About", "Services"))
        # A ``background:`` shorthand after the image hides it.
        hidden = arch.replace("background-size: cover", "background: #000")
        self.assertEqual(read_static_homepage(hidden)["images"]["hero"][0], "none")
        self.assertEqual(read_static_homepage("<t>not closed")["about"], "")

    def test_nested_section_heading_is_not_the_title(self):
        arch = (
            '<t><section data-name="SEC1"><section><h2>Nested</h2></section>'
            "<div><h2>Own &amp; only</h2></div></section></t>"
        )
        self.assertEqual(read_static_homepage(arch)["intro_title"], "Own & only")

    def test_classify_url(self):
        cases = {
            "/web/image/ir.attachment/5/datas": ("attachment", 5),
            "/web/content/6": ("attachment", 6),
            "/web/image/7-ab12/photo.jpg": ("attachment", 7),
            "/web/image/res.partner/3/image_1920": ("partner", (3, "image_1920")),
            "https://cdn.example.com/a.jpg": ("external", None),
            # Stock snippet pictures are not the shop's.
            "/web/image/website.s_cover_default_image": ("other", None),
            "/website/static/src/img/snippets_demo/s_cover.jpg": ("other", None),
            "": ("none", None),
        }
        for url, expected in cases.items():
            self.assertEqual(classify_url(url), expected, url)
