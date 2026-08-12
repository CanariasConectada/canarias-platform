# -*- coding: utf-8 -*-
{
    "name": "Website Login Branding",
    "version": "19.0.1.1.0",
    "category": "Website",
    "summary": "Canarias Conectada and ZCA logos on all website login pages",
    "description": """
Website Login Branding
======================
Shows the Canarias Conectada logo above the auth form and the ZCA
(Zonas Comerciales Abiertas) subvention logo strip below it on the
login, signup and reset password pages of every website/microsite.
Logos are bundled as static assets.
    """,
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "depends": ["website"],
    "data": [
        "views/login_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
