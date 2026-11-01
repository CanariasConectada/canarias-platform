/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {Component} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";

/**
 * Where "back to Canarias Conectada" goes: the site root of the host the user
 * is on.
 *
 * Relative on purpose. Inside the installed app the manifest's scope is "/",
 * so "/" is the one address guaranteed to stay INSIDE the app window: an
 * absolute URL to another subdomain would leave the app and open a browser
 * sheet, with a different cookie jar on iOS. The host already decides which
 * website answers "/", exactly as it does for a visitor typing the address.
 */
export const CANARIAS_HOME_URL = "/";

/**
 * Systray entry that takes an internal user from the backend (Discuss above
 * all) back to the public website.
 *
 * Why it is needed: the app installed from the website opens "/" and the
 * merchant, admin or community guest logs in from there, which lands them in
 * /odoo. The installed app has no address bar and no back button on iOS, and
 * nothing in the backend links to the public site for a user who is not a
 * website editor, so the only way home was killing the app.
 *
 * A plain link rather than an action: this is a full navigation out of the
 * web client, and a real `href` keeps long-press / middle-click working on a
 * desktop browser.
 */
export class CanariasHomeSystray extends Component {
    static template = "website_pwa.CanariasHomeSystray";
    static props = {};

    get homeUrl() {
        return CANARIAS_HOME_URL;
    }

    get title() {
        return _t("Go to the Canarias Conectada website");
    }
}

export const canariasHomeSystrayItem = {
    Component: CanariasHomeSystray,
};

/**
 * The same destination in the user menu, which is where the mobile web client
 * collects its entries (the burger menu), and where a user who does not
 * recognise the icon looks for a way out.
 */
export function canariasHomeUserMenuItem() {
    return {
        type: "item",
        id: "canarias_home",
        description: _t("Canarias Conectada website"),
        href: CANARIAS_HOME_URL,
        callback: () => {
            browser.location.assign(CANARIAS_HOME_URL);
        },
        sequence: 5,
    };
}

// Highest sequence renders leftmost: the systray is listed in reverse, so
// this sits before the call, messaging and activity menus instead of being
// squeezed between them.
registry
    .category("systray")
    .add("website_pwa.canarias_home", canariasHomeSystrayItem, {sequence: 110});
registry
    .category("user_menuitems")
    .add("website_pwa.canarias_home", canariasHomeUserMenuItem);
