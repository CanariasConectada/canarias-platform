{
    "name": "Zones Toolbar Fix",
    "version": "19.0.1.1.0",
    "summary": "Toolbar para zonas comerciales",
    "description": "Agrega el toolbar de contador y controles a las zonas comerciales",
    "author": "MikeColangelo",
    "license": "LGPL-3",
    "depends": ["website", "website_sale", "microsite_zones"],
    "data": [
        "views/toolbar.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "zones_toolbar_fix/static/src/css/zones_toolbar.css",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
    "category": "Website",
    "website": "https://github.com/CanariasConectada/canarias-platform",
}
