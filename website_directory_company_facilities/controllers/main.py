# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from werkzeug.urls import url_encode

from odoo.http import request

from odoo.addons.website_directory.controllers.main import WebsiteDirectory

# Name of the query string parameter, and the separator inside it. Commas
# rather than one parameter per facility so a shared link stays readable and
# the pager keeps a single argument to carry across pages.
PARAM = "facility"
SEPARATOR = ","


class WebsiteDirectoryFacilities(WebsiteDirectory):
    """Plug the facilities filter into the directory extension hooks.

    Everything here goes through the hooks ``website_directory`` already
    publishes for bridges. Nothing about the base directory changes: without
    this module installed the parameter is unknown and simply ignored.
    """

    # ------------------------------------------------------------------
    # Reading the visitor's choice
    # ------------------------------------------------------------------
    def _selected_facility_ids(self, kw):
        """The ids in the query string, as ids that actually exist.

        A query string is written by whoever is holding the address bar, so
        every value is checked against the catalogue before it reaches a
        domain. Junk is dropped silently rather than raising: a mistyped URL
        should show the directory, not a traceback.
        """
        raw = kw.get(PARAM) or ""
        candidates = []
        for chunk in raw.split(SEPARATOR):
            chunk = chunk.strip()
            if chunk.isdigit():
                candidates.append(int(chunk))
        if not candidates:
            return []
        existing = (
            request.env["company.facility"]
            .sudo()
            .search([("id", "in", candidates)])
            .ids
        )
        # The visitor's order is kept so the chips do not jump around.
        return [item for item in candidates if item in existing]

    # ------------------------------------------------------------------
    # Directory hooks
    # ------------------------------------------------------------------
    def _get_extra_filter_domain(self, kw):
        """One leaf per tick, which is what makes several ticks narrow.

        A single ``("...", "in", ids)`` leaf would mean "offers ANY of these",
        so asking for step-free access and parking would return shops with
        only a ramp. Amenity filters are read as promises: everything ticked
        has to be true of every shop that comes back.
        """
        domain = super()._get_extra_filter_domain(kw)
        for facility_id in self._selected_facility_ids(kw):
            domain += [("company_id.facility_ids", "in", [facility_id])]
        return domain

    def _get_extra_pager_args(self, kw):
        args = super()._get_extra_pager_args(kw)
        selected = self._selected_facility_ids(kw)
        if selected:
            args[PARAM] = SEPARATOR.join(str(item) for item in selected)
        return args

    def _prepare_directory_values(self, page=1, zone=None, url="/comercio", **kw):
        values = super()._prepare_directory_values(page=page, zone=zone, url=url, **kw)
        selected = self._selected_facility_ids(kw)
        values["selected_facility_ids"] = selected
        values["facility_filter_groups"] = self._facility_filter_groups(
            selected, zone, url, kw
        )
        values["facility_filter_clear_url"] = self._facility_url(url, kw, [])
        # One "remove just this one" URL per ticked facility, for the top
        # active-filters chip -- QWeb cannot call a controller method
        # directly, so it is precomputed here the same way the pill URLs
        # already are in ``_facility_filter_groups``.
        values["facility_remove_urls"] = {
            facility_id: self._facility_url(
                url, kw, [item for item in selected if item != facility_id]
            )
            for facility_id in selected
        }
        return values

    # ------------------------------------------------------------------
    # Building the panel
    # ------------------------------------------------------------------
    def _facility_pool(self, zone, kw):
        """The whole active catalogue, always -- not what shops happen to offer.

        Changed on 2026-08-21 from "derived from the current listing" (a shop
        with a ramp made "Rampa de acceso" appear, nothing else did) to the
        full catalogue: as of that date only 1 of 216 companies had ANY
        facility assigned at all, so the derived panel showed two threadbare
        groups and hid entire categories -- "Familia y mascotas" included,
        with real, active, always-relevant items -- purely because nobody had
        adopted them yet. A panel that only shows what has already been
        picked can never be how a merchant discovers there is something to
        pick. ``category_id.active`` is still the one gate: an archived
        category (or an archived individual facility) drops out on its own,
        same as before -- the parameters are kept for that signature and for
        callers that still narrow by zone/search, even though the pool itself
        no longer depends on them.
        """
        return (
            request.env["company.facility"]
            .sudo()
            .search([("category_id.active", "=", True)])
        )

    def _facility_url(self, url, kw, facility_ids):
        """The current address with the ticks replaced by ``facility_ids``.

        Every other filter is carried over verbatim. Building this server side
        rather than in the template is what stops a click on "parking" from
        silently throwing away the search box and the category.
        """
        args = {
            key: value
            for key, value in kw.items()
            # `page` is dropped on purpose: changing the filter changes how
            # many results there are, and page 7 of the old answer is rarely
            # page 7 of the new one.
            if key not in (PARAM, "page") and value
        }
        if facility_ids:
            args[PARAM] = SEPARATOR.join(str(item) for item in facility_ids)
        query = url_encode(args)
        return "%s?%s" % (url, query) if query else url

    def _facility_filter_groups(self, selected, zone, url, kw):
        """The panel, grouped by subdivision, in catalogue order.

        Same grouping the shop's own page uses, so a visitor who read
        "Instalaciones y servicios" on a microsite meets the same headings
        here.
        """
        pool = self._facility_pool(zone, kw)
        groups = []
        for category in pool.category_id.sorted(lambda rec: (rec.sequence, rec.id)):
            items = pool.filtered(
                lambda facility, category=category: facility.category_id == category
            ).sorted(lambda rec: (rec.sequence, rec.name or ""))
            entries = []
            for facility in items:
                is_selected = facility.id in selected
                remaining = [item for item in selected if item != facility.id]
                entries.append(
                    {
                        "id": facility.id,
                        "name": facility.name,
                        "icon": facility.icon or category.icon or "fa-check",
                        "selected": is_selected,
                        "url": self._facility_url(
                            url,
                            kw,
                            remaining if is_selected else selected + [facility.id],
                        ),
                    }
                )
            if entries:
                groups.append(
                    {
                        "id": category.id,
                        "name": category.name,
                        "icon": category.icon,
                        "facilities": entries,
                    }
                )
        return groups
