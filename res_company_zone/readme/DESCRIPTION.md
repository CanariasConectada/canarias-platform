Stores the commercial zone (Guanarteme, Tamaraceite, Lomo los Frailes) of
each business and feeds it to its public directory entry.

``website_directory`` shipped ``_get_directory_zone()`` as an explicit
extension hook returning the global zone "until the new zone module lands".
This is that module.

It also lets a company answer to its trade name, the ``comercial`` field
``l10n_es_partner`` puts on the partner: the Settings › Companies list and
search box, every company dropdown and the company switcher match the trade
name and show it first, as ``TRADE NAME (Legal Name)``. For a third of the
shops the legal name is the owner's own name, and nobody types it first.

The switcher needs its own override: ``web`` builds its labels from
``res.company.name``, never from ``display_name``.
