/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {Store} from "@mail/core/common/store_service";
import {browser} from "@web/core/browser/browser";
import {isAndroid} from "@web/core/browser/feature_detection";
import {patch} from "@web/core/utils/patch";

/** Two orders within this window chime once. */
export const ORDER_CHIME_MIN_INTERVAL_MS = 2000;

/**
 * Tells `discuss_community`'s throttle (static/src/backend/message_chime.js)
 * that this play is an ORDER, not a message. That throttle is for chat
 * bursts; a new order must never be swallowed because a chat message rang
 * a second earlier. Core's `play` ignores the unknown option.
 */
export const ORDER_SOUND_KIND = "order";

let lastOrderChimeAt = null;

/** Test hook: forget the last order chime. */
export function resetOrderChime() {
    lastOrderChimeAt = null;
}

/**
 * Chime for a new-order push that core's backend worker has just shown.
 *
 * Core's worker posts `notification-displayed` for every push it shows, but
 * the web client only sounds for Discuss records. Core's own checks are
 * kept (the "message sound" switch, main tab only, Android left to the push
 * notification, which sounds there itself); the throttle is this module's
 * own, per kind, so chat never mutes an order.
 *
 * @returns {Promise<boolean>} whether the sound was requested
 */
export async function playOrderChime(store, now = Date.now()) {
    const services = store.env.services;
    const outOfFocus = services["mail.out_of_focus"];
    if (isAndroid() && browser.Notification?.permission === "granted") {
        return false;
    }
    if (!outOfFocus.canPlayAudio || !store.settings.messageSound) {
        return false;
    }
    if (!(await outOfFocus.multiTab.isOnMainTab())) {
        return false;
    }
    if (
        lastOrderChimeAt !== null &&
        Math.abs(now - lastOrderChimeAt) < ORDER_CHIME_MIN_INTERVAL_MS
    ) {
        return false;
    }
    lastOrderChimeAt = now;
    services["mail.sound_effects"].play("new-message", {ccKind: ORDER_SOUND_KIND});
    return true;
}

patch(Store.prototype, {
    onPushNotificationDisplayed(payload) {
        super.onPushNotificationDisplayed(...arguments);
        if (payload?.model === "sale.order") {
            playOrderChime(this);
        }
    },
});
