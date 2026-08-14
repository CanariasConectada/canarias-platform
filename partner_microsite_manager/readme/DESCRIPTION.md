Merchant microsite content managed from the company form.

In the Canarias Conectada platform every merchant is a `res.company` with
its own website (native Odoo multi-website). This module adds a
**Microsite** tab on the company form where the merchant content is
edited: trade name, hero image, opening hours, delivery and parking
information, about/services sections, banners and an embeddable map.

The public homepage is a **dynamic QWeb template** that reads those fields
at render time: saving the company form updates the live page immediately.
There is no HTML generation, no view rewriting and no synchronization
step. A one-time **Publish Homepage** action installs the template as the
homepage of the company website; from then on everything is live.

The contact form on `res.partner` keeps a *Microsite* smart button that
jumps to the owning company, since users often land on the contact first.
