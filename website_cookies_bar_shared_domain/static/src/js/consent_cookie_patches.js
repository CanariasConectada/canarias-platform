/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import { cookie } from "@web/core/browser/cookie";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { CookiesBar } from "@website/interactions/cookies/cookies_bar";
import {
    CONSENT_COOKIE,
    DEFAULT_TTL,
    promoteHostOnlyConsent,
    sharedDomainForHost,
    writeSharedConsent,
} from "@website_cookies_bar_shared_domain/js/shared_consent_cookie";

// `document.cookie` as core reaches it, so whatever replaces
// `cookie._cookieMonster` (tests) replaces it here too.
const jar = {
    get cookie() {
        return cookie._cookieMonster;
    },
    set cookie(value) {
        cookie._cookieMonster = value;
    },
};

/**
 * @returns {string} the shared consent domain for THIS page, "" when the
 *  parameter is empty or the current hostname is outside of it.
 */
function activeSharedDomain() {
    return sharedDomainForHost(window.location.hostname, session.cookies_bar_shared_domain);
}

function isSecurePage() {
    return window.location.protocol === "https:";
}

// Every writer of the consent funnels through `cookie.set`: the cookies bar
// (`Popup.onHideModal`) and the pre-16.0 cleanup (`cookie.delete`, which calls
// `set`). Any other key, and this key whenever no shared domain applies, goes
// to core untouched.
patch(cookie, {
    set(key, value, ttl, type) {
        const domain = key === CONSENT_COOKIE && value !== undefined && activeSharedDomain();
        if (!domain) {
            return super.set(key, value, ttl, type);
        }
        // Same gate as the `website` patch of `set` (http_cookie.js), which is
        // bypassed here. The consent itself is a "required" cookie.
        const isAllowed = this.isAllowedCookie ? this.isAllowedCookie(type || "required") : true;
        writeSharedConsent(jar, {
            value,
            ttl: isAllowed ? ttl ?? DEFAULT_TTL : 0,
            domain,
            secure: isSecurePage(),
        });
    },
});

patch(CookiesBar.prototype, {
    setup() {
        // Before `super`: `Popup.setup()` decides there whether the bar was
        // already answered, and must not be fooled by a stale host-only value
        // shadowing the shared one.
        const domain = activeSharedDomain();
        if (domain) {
            const nbDays = Number(this.el.querySelector(".modal")?.dataset.consentsDuration);
            promoteHostOnlyConsent(jar, {
                domain,
                secure: isSecurePage(),
                ttl: nbDays > 0 ? nbDays * 24 * 60 * 60 : DEFAULT_TTL,
            });
        }
        super.setup();
    },
});
