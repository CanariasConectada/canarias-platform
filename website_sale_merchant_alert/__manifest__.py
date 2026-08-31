# Copyright 2026 Canarias Conectada
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

{
    "name": "Website Sale Merchant Alert",
    "summary": "Email the shop owner when their website receives an order",
    "version": "19.0.1.0.0",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "category": "Website",
    "license": "AGPL-3",
    "depends": ["website_sale"],
    "data": [
        "data/mail_template.xml",
    ],
    "installable": True,
}
