# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class WebsitePage(models.Model):
    _inherit = "website.page"

    @api.model
    def _get_cache_key(self, request):
        """Make the public page cache aware of the homepage banner.

        Website pages are cached per (website, language, path) for up to an
        hour. Without this, opening or closing a campaign (or crossing its
        first/last day) would leave the old homepage on screen for that long.
        The key carries the banner campaign and its last write, so the cached
        copy changes the moment the campaign does. Off the homepage the helper
        answers without a search.
        """
        key = super()._get_cache_key(request)
        campaign = request.website._raffle_banner_campaign()
        return key + ((campaign.id, campaign.write_date) if campaign else (0,),)
