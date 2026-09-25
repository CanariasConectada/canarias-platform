/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {Component, useState} from "@odoo/owl";
import {DiscussClientAction} from "@mail/core/public_web/discuss_client_action";
import {browser} from "@web/core/browser/browser";
import {useService} from "@web/core/utils/hooks";

/** sessionStorage key: dismissed for this browser session only. */
export const BANNER_DISMISSED_KEY = "discuss_community.notification_banner_dismissed";

function readDismissed() {
    try {
        return browser.sessionStorage.getItem(BANNER_DISMISSED_KEY) === "1";
    } catch {
        return false;
    }
}

/**
 * "Turn on notifications" banner at the top of Discuss.
 *
 * Shown to every user (guests, merchants, staff) until the browser grants
 * the permission. Insistent on purpose: closing it only hides it for the
 * current browser session, and it comes back on the next one. When the
 * permission was denied, clicking can no longer prompt, so the banner
 * explains how to re-enable it from the browser or device settings instead.
 *
 * Asking is core's job (`mail.notification.permission`), and so is the push
 * subscription: `mail`'s web client subscribes the device as soon as the
 * permission turns to "granted".
 */
export class DiscussNotificationBanner extends Component {
    static template = "discuss_community.DiscussNotificationBanner";
    static props = {};

    setup() {
        this.permission = useState(useService("mail.notification.permission"));
        this.state = useState({dismissed: readDismissed()});
    }

    get isVisible() {
        return !this.state.dismissed && this.permission.permission !== "granted";
    }

    get isDenied() {
        return this.permission.permission === "denied";
    }

    async onClickEnable() {
        await this.permission.requestPermission();
    }

    onClickDismiss() {
        this.state.dismissed = true;
        try {
            browser.sessionStorage.setItem(BANNER_DISMISSED_KEY, "1");
        } catch {
            // Storage unavailable (private mode): hidden until reload.
        }
    }
}

DiscussClientAction.components = {
    ...DiscussClientAction.components,
    DiscussNotificationBanner,
};
