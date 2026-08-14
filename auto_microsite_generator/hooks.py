# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)


def uninstall_hook(env):
    """Remove the auto-generated microsite homepages before the module is dropped.

    The homepage views/pages are created at runtime (see
    ``res.company._ensure_microsite_homepage``), not from data files, so they
    are not tracked in ``ir.model.data`` and would survive ``module_uninstall``.
    Their arch ``t-call``s ``auto_microsite_generator.default_homepage_content``,
    a template that IS removed with the module, so leaving them behind renders a
    500 on every microsite homepage. Delete them defensively here.
    """
    View = env["ir.ui.view"].sudo()
    generated_views = View.search(
        [("key", "=like", "auto_microsite_generator.homepage_%")]
    )
    if not generated_views:
        return
    pages = (
        env["website.page"]
        .sudo()
        .search([("view_id", "in", generated_views.ids)])
    )
    _logger.info(
        "auto_microsite_generator uninstall: removing %s generated page(s) and "
        "%s view(s).",
        len(pages),
        len(generated_views),
    )
    # Pages first: they reference the views through a required view_id.
    pages.unlink()
    generated_views.exists().unlink()
