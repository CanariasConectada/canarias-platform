Turns each public website into an installable app.

Odoo ships a PWA for the backend only: ``/web/manifest.webmanifest`` is scoped
to ``/odoo`` and carries Odoo icon, so installing it gives the visitor the ERP
instead of the shop. OCA ``web_pwa_customize`` customises that same backend
app, and ``OCA/pwa-builder`` is an empty repository on 16.0, 18.0 and 19.0.
Nothing covered the public side.
