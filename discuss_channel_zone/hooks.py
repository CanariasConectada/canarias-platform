# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Seat the accounts that already existed when the module was installed.

    The create/write triggers only cover accounts that change AFTER the
    install, so without this a platform with an existing user base would
    install four empty channels and wait for the first nightly cron. The hook
    is literally the cron: one code path, so "install" and "reconcile" cannot
    drift apart.
    """
    counters = env["res.users"]._cron_sync_zone_channels()
    _logger.info(
        "discuss_channel_zone: initial sync seated %s memberships",
        counters["added"],
    )
