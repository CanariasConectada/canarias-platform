"""Compact homepage archs for the rebuild tests: a standard skeleton (the
reference and the "well formed" sites) in several languages and a legacy
``s_adventure`` layout. Structure mirrors the real views (3218, 4927)."""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_apply_lib as lib  # noqa: E402
import jev_rebuild_lib as rb  # noqa: E402
import jev_rebuild_terms as terms  # noqa: E402

LANGS = ("es_ES", "en_US", "de_DE")

# Template vocabulary per language (what the reference view carries).
TEMPLATE = {
    "es_ES": dict(shop="Tienda", hours="Horario", parking="Parking", more="Leer más", write="ESCRÍBENOS",
                  name="Nombre", send="Enviar", find="ENCUÉNTRANOS", grants="Subvenciones",
                  strip="Consume Productos Canarios"),
    "en_US": dict(shop="Shop", hours="Opening hours", parking="Parking", more="Read more", write="WRITE TO US",
                  name="Name", send="Send", find="FIND US", grants="Grants", strip="Consume Canary Products"),
    "de_DE": dict(shop="Laden", hours="Zeitplan", parking="Parken", more="Lesen Sie mehr", write="SCHREIBER",
                  name="Name", send="Senden", find="FINDEN SIE UNS", grants="Zuschüsse",
                  strip="Verbrauch Produkte Kanarische Inseln"),
}

HERO = '''<section class="s_cover parallax pt96 pb96" data-snippet="s_cover" data-name="Hero" style="background-image: url('/web/image/res.company/{cid}/microsite_hero_image'); background-size: cover; position: relative;">
    <div class="s_allow_columns container">
        <h1 class="display-1" style="text-align: center;">
            <span class="display-4-fs">{h1}</span>
        </h1>
        <p style="text-align: center;">
            <a class="btn btn-lg btn-primary o_translate_inline" href="/shop">{shop}</a>
        </p>
    </div>
</section>'''
HORARIO = '''<section class="s_features pt48 pb48" data-snippet="s_features" data-name="Horario" t-if="website.company_id.sudo()._microsite_live_has('features') or editable">
    <div class="container">
        <div class="row justify-content-center">
            <div class="col-lg-4 text-center" t-if="website.company_id.sudo()._microsite_live_has('hours') or editable">
            <span class="fa fa-clock-o fa-2x mb-3" style="display: block;"/>
            <h5 class="fw-bold">{hours}</h5>
            <t t-call="partner_microsite_manager.microsite_opening_hours_card"/>
        </div><div class="col-lg-4 text-center" t-if="website.company_id.sudo()._microsite_live_has('parking') or editable">
            <h5 class="fw-bold">{parking}</h5>
            <p class="text-muted"><t t-call="partner_microsite_manager.microsite_live_parking"/></p>
        </div>
        </div>
    </div>
</section>'''
SEC1 = '''<section class="s_kickoff o_cc o_cc5 pt104 pb120" data-snippet="s_kickoff" data-name="SEC1" style="background-image: url('/web/image/res.company/{cid}/microsite_intro_image'); position: relative;">
    <div class="container" style="position: relative; z-index: 1;">
        <h2 class="h3-fs text-center text-white">{sec1}</h2>
    </div>
</section>'''
COLUMN = '''<div class="border o_colored_level col-lg-6 text-center pt-4 pb-4" data-name="Column">
            <span class="fa {icon} fa-3x mb-3" style="display: block;"/>
            <h6 class="text-center">{title}</h6>
            <small class="text-muted d-block" style="padding: 0 20px;">{excerpt}</small>
            <div class="mt-3 text-center">
                <a href="#acerca{n}_{slug}" data-bs-toggle="collapse" class="btn btn-primary rounded-pill px-4">{more}</a>
            </div>
            <div id="acerca{n}_{slug}" class="collapse mt-3">
                <div class="card card-body bg-light">{text}</div>
            </div>
        </div>'''
ACERCA = '''<section class="s_attributes_vertical o_colored_level pt48 pb56" data-snippet="s_attributes_vertical" data-name="Acerca">
    <div class="container">
        <div class="row justify-content-center">
            {col1}{col2}
        </div>
    </div>
</section>'''
SEPARADOR = '''<section class="s_kickoff o_cc o_cc5 pt104 pb120 o_colored_level" data-snippet="s_kickoff" data-name="Separador" style="background-image: url('/web/image/res.company/{cid}/microsite_banner_image'); position: relative;">
    <div class="container" style="position: relative; z-index: 1;">
        <h2 class="h3-fs text-center text-white">{strip}</h2>
    </div>
</section>'''
CALLS = ('<t t-set="cf_company" t-value="website.company_id.sudo()"/><t t-call="company_facilities.facilities_block"/>\n'
         '<t t-set="cc_company" t-value="website.company_id"/><t t-call="company_certification.certification_block"/>')
FORM = '''<section class="s_website_form pt48 pb48" data-snippet="s_website_form" data-name="Formulario">
    <div class="container">
        <div class="row">
            <div class="col-lg-6 pb16">
                <h4 class="mb-3"><span class="fa fa-envelope" style="margin-right: 8px;"/><strong>{write}</strong></h4>
                <form action="/website/form/" method="post" data-model_name="crm.lead">
                    <label class="s_website_form_label"><span class="s_website_form_label_content">{name}</span><span class="s_website_form_mark"> *</span></label>
                    <input type="text" class="form-control s_website_form_input" name="contact_name" required=""/>
                    <button type="submit" class="btn btn-primary">{send}</button>
                </form>
            </div>
            <div class="col-lg-6">
                <iframe width="100%" height="200" data-cc-live="map" t-att-src="website.company_id.sudo()._get_microsite_map_url()" t-if="website.company_id.sudo()._microsite_live_has('map') or editable"/>
                <h4 class="mb-3"><span class="fa fa-map-marker" style="margin-right: 8px;"/><strong>{find}</strong></h4>
                <p class="mb-2" t-if="website.company_id.sudo()._microsite_live_has('address') or editable"><t t-call="partner_microsite_manager.microsite_live_address"/></p>
            </div>
        </div>
    </div>
</section>'''
SUBV = '''<section class="s_picture pt64 pb64 o_colored_level" data-snippet="s_picture" data-name="Subvenciones">
    <div class="container">
        <img src="/web/image/952/subvenciones.png" class="figure-img img-fluid rounded" alt="{grants}" loading="lazy"/>
    </div>
</section>'''


def wrap(slug: str, body: str, name: str | None = None) -> str:
    name = f"Home - {slug}" if name is None else name
    return (f'<t name="{name}" t-name="website.homepage_{slug}">\n    <t t-call="website.layout">\n'
            f'        <div id="wrap" class="oe_structure oe_empty">\n            {body}\n        </div>\n    </t>\n</t>')


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def column(n: int, slug: str, lang: str, title: str, text: str, excerpt: str | None = None) -> str:
    return COLUMN.format(n=n, slug=slug, icon="fa-book" if n == 1 else "fa-cogs", title=esc(title), text=esc(text),
                         excerpt=esc(excerpt if excerpt is not None else lib.acerca_preview(text)),
                         more=TEMPLATE[lang]["more"])


def standard_arch(lang: str, cid: int, slug: str, h1: str, sec1: str, cols: dict[int, tuple[str, str]],
                  strip: str | None = None) -> str:
    """Reference-shaped homepage of one language."""
    t = TEMPLATE[lang]
    parts = [HERO.format(cid=cid, h1=esc(h1), shop=t["shop"]), HORARIO.format(**t), SEC1.format(cid=cid, sec1=esc(sec1)),
             ACERCA.format(col1=column(1, slug, lang, *cols[1]), col2=column(2, slug, lang, *cols[2])),
             SEPARADOR.format(cid=cid, strip=esc(strip or t["strip"])), CALLS, FORM.format(**t), SUBV.format(**t)]
    return wrap(slug, "\n".join(parts))


# Reference company (what must never leak into another site).
REF = dict(cid=51, slug="flashprint")
REF_TEXTS = {
    "es_ES": ("Flash Print", "Flash Print: tu referente en Guanarteme.",
              {1: ("Nuestra historia", "Flash Print es un negocio referente."), 2: ("Servicios", "Entre nuestros servicios destacan.")}),
    "en_US": ("Flash Print", "Flash Print: your reference in Guanarteme.",
              {1: ("Our story", "Flash Print is a reference business."), 2: ("Services", "Our services stand out.")}),
    "de_DE": ("Flash Print", "Flash Print: Ihre Referenz in Guanarteme.",
              {1: ("Unsere Geschichte", "Flash Print ist ein Referenzgeschäft."), 2: ("Dienstleistungen", "Unsere Dienstleistungen.")}),
}
SITE_TEXTS = {
    "es_ES": ("Área Surf & Skate", "Tienda de surf en Guanarteme.",
              {1: ("Sobre nosotros", "Área Surf es una tienda para los que viven el mar."), 2: ("Nuestros servicios", "Tablas y accesorios.")},
              "Consume Productos Canarios"),
    "en_US": ("Área Surf & Skate", "Surf shop in Guanarteme.",
              {1: ("About us", "Área Surf is a shop for those who live the sea."), 2: ("Our services", "Boards and accessories.")},
              "Consume Canary Products"),
    "de_DE": ("Área Surf & Skate", "Surfshop in Guanarteme.",
              {1: ("Über uns", "Área Surf ist ein Geschäft für Meeresliebhaber."), 2: ("Unsere Dienstleistungen", "Boards und Zubehör.")},
              "Verbrauch Produkte Kanarische Inseln"),
}
SITE = dict(cid=285, slug="areasurf")


def reference_archs() -> dict[str, str]:
    return {lang: standard_arch(lang, REF["cid"], REF["slug"], *REF_TEXTS[lang]) for lang in LANGS}


def deviating_archs(drop: tuple[str, ...] = ("Horario", "Separador")) -> dict[str, str]:
    """The site rendered on the standard skeleton minus ``drop`` sections
    (areasurf: no Horario, no Separador)."""
    archs = {}
    for lang in LANGS:
        arch = standard_arch(lang, SITE["cid"], SITE["slug"], *SITE_TEXTS[lang])
        for name in drop:
            arch = rb._remove_section(arch, name)
        archs[lang] = arch
    return archs


PORTADA = '''<section class="s_adventure pt184 pb200 o_colored_level" data-snippet="s_adventure" data-name="Portada" style="background-image: url('/web/image/res.company/{cid}/microsite_hero_image'); position: relative;">
    <div class="s_allow_columns container">
        <h1 class="display-1" style="text-align: center;">{h1}</h1>
        <p style="text-align: center;"><a class="btn btn-lg btn-primary o_translate_inline" href="/shop">{shop}</a></p>
    </div>
</section>'''
INFO_BAR = '''<section class="s_attributes_vertical o_colored_level" data-snippet="s_attributes_vertical" data-name="Info Bar">
    <div class="container-fluid"><div class="row justify-content-center">
        <div class="col-lg-4 border text-center" data-name="Column" data-cc-card="hours"><h6 class="text-center">{hours}</h6><t t-call="partner_microsite_manager.microsite_opening_hours_card"/></div>
    </div></div>
</section>'''
FORM_CONTACTO = '''<section class="s_website_form_info o_cc o_cc2 o_colored_level pt-5 pb-4" data-snippet="s_website_form_info" data-name="Formulario Contacto">
    <div class="container"><div class="row"><div class="col-lg-6">
        <h4 class="text-center mb-3"><strong>{write}</strong></h4>
        <section class="s_website_form pt8 pb8" data-snippet="s_website_form" data-name="Formulario">
            <form action="/website/form/" method="post"><button type="submit">{send}</button></form>
        </section>
        <p class="mb-2"><i class="fa fa-envelope"/>mycompany@test.com</p>
    </div></div></div>
</section>'''
LEGACY = dict(cid=164, slug="maquifercoop")
LEGACY_TEXTS = {
    "es_ES": ("Maquifer Industrial", "Ferretería y suministros industriales.", ("Nuestra historia", "MAQUIFER es una cooperativa canaria."),
              "CONSUME PRODUCTOS CANARIOS"),
    "en_US": ("MAQUIFER INDUSTRIAL", "Hardware and industrial supplies.", ("Our story", "MAQUIFER is a Canarian cooperative."),
              "CONSUMPTION PRODUCTS CANARIES"),
    "de_DE": ("MAQUIFER INDUSTRIAL", "Eisenwaren und Industriebedarf.", ("Unsere Geschichte", "MAQUIFER ist eine kanarische Genossenschaft."),
              "VERBRAUCH PRODUKTE KANARIEN"),
}


def legacy_archs(with_sec1: bool = True) -> dict[str, str]:
    """``Portada > Info Bar > SEC1 > Acerca (one column) > Separador > calls >
    Formulario Contacto > Subvenciones`` with an odd root name."""
    archs = {}
    for lang in LANGS:
        t, (h1, sec1, col1, strip) = TEMPLATE[lang], LEGACY_TEXTS[lang]
        one = column(1, LEGACY["slug"], lang, *col1).replace("col-lg-6", "col-lg-8 offset-lg-2", 1)
        parts = [PORTADA.format(cid=LEGACY["cid"], h1=h1, shop=t["shop"]), INFO_BAR.format(**t)]
        if with_sec1:
            parts.append(SEC1.format(cid=LEGACY["cid"], sec1=sec1))
        parts += [ACERCA.format(col1=one, col2=""), SEPARADOR.format(cid=LEGACY["cid"], strip=strip), CALLS,
                  FORM_CONTACTO.format(**t), SUBV.format(**t)]
        archs[lang] = wrap(LEGACY["slug"], "".join(parts), name="Home - DiCloud - Error Interno")
    return archs


def _term_position(arch: str, term: str, cursor: int) -> int:
    """Offset of the next occurrence of ``term`` that is element text (only
    whitespace between the surrounding tags) or a translatable attribute
    value; ``data-name="Horario"`` is not a term."""
    index = arch.find(term, cursor)
    while index >= 0:
        before, after = arch[:index], arch[index + len(term):]
        if before.rstrip().endswith(">") and after.lstrip().startswith("<"):
            return index
        if after.startswith('"') and any(before.endswith(f' {attr}="') for attr in ("alt", "title", "placeholder")):
            return index
        index = arch.find(term, index + 1)
    raise AssertionError(f"term {term!r} not found as text or translatable attribute")


def translate_arch(arch: str, func) -> str:
    """Replace every term of ``arch`` (document order) by ``func(term)`` when
    that is truthy: the string-level equivalent of Odoo's ``xml_translate``
    for the clean fixtures of these tests."""
    out, cursor = [], 0
    for term in terms.extract_terms(arch):
        index = _term_position(arch, term, cursor)
        out.append(arch[cursor:index])
        out.append(func(term) or term)
        cursor = index + len(term)
    out.append(arch[cursor:])
    return "".join(out)
