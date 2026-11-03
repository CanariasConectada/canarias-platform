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

The homepages imported from the legacy platform keep their own design and
texts, but their values (contact lines, map, parking, delivery, opening
hours) are rendered from the company too: the importer's literal values
were replaced by small live templates (`views/microsite_live_data.xml`),
and saving such a page in the website builder puts them back if the
builder flattened them.

The contact form on `res.partner` keeps a *Microsite* smart button that
jumps to the owning company, since users often land on the contact first.
