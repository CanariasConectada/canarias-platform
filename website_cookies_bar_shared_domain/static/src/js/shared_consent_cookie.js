/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

// Pure helpers behind the shared cookies bar consent. This file imports
// NOTHING on purpose: `tests/shared_consent_harness.js` runs these exact bytes
// in `node` against an emulated browser cookie store.
//
// Every function takes a `jar`: any object whose `cookie` property behaves
// like `document.cookie` (reading lists `name=value` pairs, assigning stores
// one cookie).
//
// A script cannot ask the browser whether a cookie is host-only or carries a
// `Domain`: `document.cookie` only lists names and values. Everything below
// works around that one limitation by expiring the host-only cookie and
// looking at what is left.

export const CONSENT_COOKIE = "website_cookies_bar";

// Same default as `@web/core/browser/cookie` (not exported there).
export const DEFAULT_TTL = 24 * 60 * 60 * 365;

const LABEL_RE = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;
const MAX_DOMAIN_LENGTH = 253;
// Mirror of `_PUBLIC_SECOND_LEVEL_LABELS` in models/website.py.
const PUBLIC_SECOND_LEVEL_LABELS = new Set([
    "ac",
    "co",
    "com",
    "edu",
    "go",
    "gob",
    "gov",
    "int",
    "mil",
    "ne",
    "net",
    "nom",
    "or",
    "org",
]);

// Mirror of `_PUBLIC_SUFFIX_DENYLIST` in models/website.py.
const PUBLIC_SUFFIX_DENYLIST = new Set([
    "amazonaws.com",
    "azurewebsites.net",
    "blogspot.com",
    "cloudfront.net",
    "firebaseapp.com",
    "github.io",
    "gitlab.io",
    "herokuapp.com",
    "netlify.app",
    "odoo.com",
    "pages.dev",
    "vercel.app",
    "web.app",
]);

/**
 * Mirror of `normalize_shared_domain` in models/website.py. The server has
 * already validated the value; validating again costs nothing and keeps a
 * stale cached page or a tampered `session_info` from widening the cookie.
 *
 * @param {unknown} value
 * @returns {string} the registrable domain, or "" when invalid
 */
export function normalizeSharedDomain(value) {
    let domain = typeof value === "string" ? value.trim().toLowerCase() : "";
    if (domain.startsWith(".")) {
        domain = domain.slice(1);
    }
    if (domain.endsWith(".")) {
        domain = domain.slice(0, -1);
    }
    if (!domain || domain.length > MAX_DOMAIN_LENGTH) {
        return "";
    }
    const labels = domain.split(".");
    if (labels.length < 2 || !labels.every((label) => LABEL_RE.test(label))) {
        return "";
    }
    if (/^[0-9]+$/.test(labels[labels.length - 1])) {
        return "";
    }
    if (
        labels.length === 2 &&
        labels[1].length === 2 &&
        PUBLIC_SECOND_LEVEL_LABELS.has(labels[0])
    ) {
        return "";
    }
    if (PUBLIC_SUFFIX_DENYLIST.has(domain)) {
        return "";
    }
    return domain;
}

/**
 * The hostname guard: the shared domain applies only to the domain itself and
 * to its subdomains. localhost, an IP, a lab host or a custom shop domain get
 * "" and therefore keep core's host-only cookie.
 *
 * @param {string} hostname `window.location.hostname`
 * @param {unknown} configured value handed over by the server
 * @returns {string} the domain to put in `Domain=`, or ""
 */
export function sharedDomainForHost(hostname, configured) {
    const domain = normalizeSharedDomain(configured);
    let host = typeof hostname === "string" ? hostname.trim().toLowerCase() : "";
    if (host.endsWith(".")) {
        host = host.slice(0, -1);
    }
    if (domain && (host === domain || host.endsWith(`.${domain}`))) {
        return domain;
    }
    return "";
}

/**
 * Every value `cookieString` holds for `name`: two when a host-only cookie
 * and a `Domain` cookie coexist.
 *
 * @param {string} cookieString
 * @param {string} name
 * @returns {string[]}
 */
export function readAllValues(cookieString, name) {
    const values = [];
    for (const part of (cookieString || "").split("; ")) {
        const [key, value] = part.split(/=(.*)/);
        if (key === name) {
            values.push(value || "");
        }
    }
    return values;
}

/**
 * @param {string} raw
 * @returns {{optional: boolean, ts: number}|null} null unless `raw` is a
 *  consent in the current (16.0+) format
 */
export function parseConsent(raw) {
    try {
        const consent = JSON.parse(raw);
        if (!consent || typeof consent !== "object" || !("optional" in consent)) {
            return null;
        }
        const ts = Number(consent.ts);
        return { optional: Boolean(consent.optional), ts: Number.isFinite(ts) && ts > 0 ? ts : 0 };
    } catch {
        return null;
    }
}

/**
 * @param {string} raw
 * @returns {boolean} whether `raw` is a consent in the current (16.0+) format
 */
export function isConsentValue(raw) {
    return parseConsent(raw) !== null;
}

/**
 * Which of several stored consents is the visitor's. Decided on the VALUES
 * alone, because a script cannot know which cookie each one came from.
 *
 * 1. A refusal (`optional: false`) beats an acceptance, whatever their source
 *    or age. Deliberately asymmetric: a stale or forged cookie may make the
 *    platform ask for LESS than the visitor allowed, never for more. To accept
 *    again the visitor uses the bar, which writes the shared cookie directly.
 * 2. Same `optional`: the most recent `ts` wins.
 * Unparsable values (legacy `"true"`, garbage) count as absent.
 *
 * @param {string[]} values
 * @returns {string|null} the winning raw value, null when none is usable
 */
export function resolveConsent(values) {
    let winner = null;
    for (const raw of values) {
        const consent = parseConsent(raw);
        if (!consent) {
            continue;
        }
        if (
            !winner ||
            (winner.consent.optional && !consent.optional) ||
            (winner.consent.optional === consent.optional && consent.ts > winner.consent.ts)
        ) {
            winner = { raw, consent };
        }
    }
    return winner && winner.raw;
}

/**
 * @param {Object} params
 * @param {string} params.value
 * @param {number} params.ttl seconds; 0 expires the cookie
 * @param {string} [params.domain] omitted = host-only, exactly like core
 * @param {boolean} [params.secure]
 * @returns {string}
 */
export function buildConsentCookie({ value, ttl, domain, secure }) {
    const parts = [`${CONSENT_COOKIE}=${value}`, "path=/", `max-age=${Math.floor(ttl)}`];
    if (domain) {
        parts.push(`domain=${domain}`, "SameSite=Lax");
        if (secure) {
            parts.push("Secure");
        }
    }
    return parts.join("; ");
}

function expireHostOnly(jar) {
    jar.cookie = buildConsentCookie({ value: "kill", ttl: 0 });
}

/**
 * Write (or, with `ttl <= 0`, delete) the consent on the shared domain.
 *
 * The host-only cookie is expired FIRST. Afterwards would be wrong on the
 * bare domain for a browser that, as RFC 6265 literally says, identifies a
 * cookie by name + domain + path and ignores the host-only flag: there the
 * host-only expiry would take the fresh shared cookie down with it.
 *
 * If the browser refuses the `Domain` cookie (a public suffix the validation
 * heuristic does not know, a privacy extension...), the consent is written
 * host-only so the visitor is never asked on every page: that is core's
 * behaviour, no worse.
 *
 * @param {{cookie: string}} jar
 * @param {Object} params
 * @param {string} params.value
 * @param {number} params.ttl
 * @param {string} params.domain already guarded by `sharedDomainForHost`
 * @param {boolean} [params.secure]
 * @returns {"shared"|"host-only"|"deleted"}
 */
export function writeSharedConsent(jar, { value, ttl, domain, secure }) {
    expireHostOnly(jar);
    jar.cookie = buildConsentCookie({ value, ttl, domain, secure });
    if (ttl <= 0) {
        return "deleted";
    }
    if (readAllValues(jar.cookie, CONSENT_COOKIE).includes(value)) {
        return "shared";
    }
    jar.cookie = buildConsentCookie({ value, ttl });
    return "host-only";
}

/**
 * Seconds a consent given at `ts` still has to live, so that moving it never
 * renews it.
 */
function remainingTtl(raw, fullTtl, now) {
    const { ts } = parseConsent(raw);
    if (!ts || ts > now) {
        return fullTtl;
    }
    return fullTtl - Math.floor((now - ts) / 1000);
}

/**
 * Leave exactly one consent behind, on the shared domain: the visitor's.
 *
 * Runs on every page view of a host inside the shared domain. It moves a
 * consent given before this module (host-only) to the shared domain, and
 * settles the case where a host-only cookie and a shared one coexist with
 * different values.
 *
 * The steps do not depend on knowing which value is the host-only one:
 * 1. decide the winner on the values (`resolveConsent`);
 * 2. expire the host-only cookie;
 * 3. whatever is still readable is the shared cookie. If it already holds the
 *    winner it is left untouched (its lifetime included); otherwise the winner
 *    is written there with the lifetime ITS OWN `ts` leaves it, never more.
 * With no usable value (legacy pre-16.0, garbage, expired) nothing is written:
 * core discards such a consent and asks again anyway.
 *
 * @param {{cookie: string}} jar
 * @param {Object} params
 * @param {string} params.domain already guarded by `sharedDomainForHost`
 * @param {boolean} [params.secure]
 * @param {number} [params.ttl] full lifetime of a consent, in seconds
 * @param {number} [params.now] epoch milliseconds
 * @returns {"none"|"shared"|"shared-wins"|"promoted"|"host-only"|"dropped"|"ignored"}
 *  "shared": only the shared cookie existed. "shared-wins": a conflict, and
 *  the shared cookie already held the winner. "promoted": the winner had to be
 *  written on the shared domain. "host-only": the browser refused that.
 */
export function promoteHostOnlyConsent(
    jar,
    { domain, secure, ttl = DEFAULT_TTL, now = Date.now() }
) {
    const before = readAllValues(jar.cookie, CONSENT_COOKIE);
    if (!before.length) {
        return "none";
    }
    const winner = resolveConsent(before);
    expireHostOnly(jar);
    const shared = readAllValues(jar.cookie, CONSENT_COOKIE);
    if (winner === null) {
        // An unusable shared value is core's to clean up (`cookie.delete`
        // goes through the patched `set`; the server expires it too).
        return shared.length ? "ignored" : "dropped";
    }
    if (shared.length === 1 && shared[0] === winner) {
        return before.length > 1 ? "shared-wins" : "shared";
    }
    const ttlLeft = remainingTtl(winner, ttl, now);
    if (ttlLeft <= 0) {
        writeSharedConsent(jar, { value: "kill", ttl: 0, domain, secure });
        return "dropped";
    }
    const written = writeSharedConsent(jar, { value: winner, ttl: ttlLeft, domain, secure });
    return written === "shared" ? "promoted" : "host-only";
}
