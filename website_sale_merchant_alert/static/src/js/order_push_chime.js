/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {Store} from "@mail/core/common/store_service";
import {patch} from "@web/core/utils/patch";

/**
 * Chime in the open web client when core's backend worker has just shown a
 * new-order push.
 *
 * Core's worker posts `notification-displayed` for every push it shows, but
 * the web client only sounds for Discuss records. Routed through core's
 * `_playSound`, so the "message sound" switch, the main-tab rule and the
 * Android rule (the push notification itself sounds there) all apply, and
 * with `mail_push_guest` installed the 2-second throttle too.
 */
patch(Store.prototype, {
    onPushNotificationDisplayed(payload) {
        super.onPushNotificationDisplayed(...arguments);
        if (payload?.model === "sale.order") {
            this.env.services["mail.out_of_focus"]._playSound();
        }
    },
});
