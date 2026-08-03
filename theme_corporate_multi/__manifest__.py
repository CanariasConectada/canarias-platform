{
    "name": "Tema Maestro Corporativo Multi-Website",
    "summary": "Cabecera, pie y portada corporativos compartidos por todos los microsites",
    "version": "19.0.2.0.0",
    "category": "Theme/Creative",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "LGPL-3",
    # ``zones_company`` (the original dependency) is retired. Its replacement is
    # ``res_company_zone``, which stores the neighbourhood as a Selection on the
    # company instead of a many2one to a zone model.
    #
    # ``partner_microsite_manager`` is a hard dependency, not a nicety: it owns
    # the legal pages, and this theme deliberately does NOT create its own (see
    # the note at the top of views/pages.xml).
    "depends": [
        "website",
        "website_sale",
        "auth_signup",
        "res_company_zone",
        "partner_microsite_manager",
    ],
    "data": [
        "views/layout.xml",
        "views/pages.xml",
    ],
    # The original module shipped every stylesheet and script as raw <link> and
    # <script> tags injected into <head> from a QWeb template. That works, but it
    # bypasses the asset pipeline: no bundling, no cache busting, no minifying,
    # and one extra blocking request per file on every page of every microsite.
    # Two of those files were never referenced at all, so in production they
    # simply never loaded.
    #
    # ``clean_directory_menus.js`` is deliberately NOT here. It rebuilt the
    # navbar in the browser, deleting every entry whose href was missing from a
    # hard-coded allow-list: ['/', '/shop', '/directorio', '/event',
    # '/memoria-viva', '/lugares-de-interes', '/resenas', '#']. Those paths no
    # longer match the data — the directory moved to /comercio and the explora
    # pages to /explora/* — so loading it would strip /comercio (197 sites),
    # /silver-economy, /sostenibilidad, /aviso-legal, /slides and /contactus
    # from every menu. Which entries a menu carries is data, and it is fixed in
    # the menu, not undone client-side afterwards.
    "assets": {
        "web.assets_frontend": [
            "theme_corporate_multi/static/src/scss/correcciones.css",
            "theme_corporate_multi/static/src/scss/header_cleanup.scss",
            "theme_corporate_multi/static/src/js/horario_dinamico.js",
        ],
    },
    "installable": True,
    "application": False,
}
