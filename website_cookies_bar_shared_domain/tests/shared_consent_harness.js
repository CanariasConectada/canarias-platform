/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Runs the SHIPPED frontend code of this module in `node:vm` against an
 * emulated browser cookie store, so it is judged by what a browser would end
 * up storing and not by the strings it builds.
 *
 * What is real: `shared_consent_cookie.js`, `consent_cookie_patches.js`, and
 * core's own `@web/core/utils/patch`, `@web/core/browser/cookie` and
 * `@website/js/http_cookie` (the `website` patch of `cookie.set`), all loaded
 * from the addons path through a tiny ES-module loader. A typo in
 * `session.cookies_bar_shared_domain`, a wrong hostname read or a patch that
 * only works in one load order therefore fails here.
 * What is fake: `@web/session` (one key), `document`/`window.location`, and
 * `CookiesBar`, reduced to what `Popup.setup()` decides from the cookie (the
 * real class imports the whole website frontend).
 *
 * What the store models (RFC 6265 section 5.3, the parts that matter here):
 *   - a cookie without `Domain` is host-only: only the exact host reads it;
 *   - a cookie with `Domain=d` is refused unless the setting host domain-
 *     matches `d`, refused when `d` is a public suffix, and is then readable
 *     from `d` and every subdomain of `d`;
 *   - `Secure` is refused on a non-https page;
 *   - `max-age<=0` removes the cookie with the same identity;
 *   - `document.cookie` lists matching cookies, earliest creation first.
 * Identity: name + domain + path + host-only flag (Chromium, Firefox). With
 * `strictIdentity` the host-only flag is ignored, which is the literal
 * reading of the RFC: on the bare domain a host-only cookie and a `Domain`
 * cookie are then the SAME cookie and overwrite each other.
 *
 * Usage:  node shared_consent_harness.js <input.json>
 * stdout: a single JSON object. The assertions all live in Python.
 */
"use strict";

const fs = require("fs");
const vm = require("vm");

const HELPERS = "@website_cookies_bar_shared_domain/js/shared_consent_cookie";
const PATCHES = "@website_cookies_bar_shared_domain/js/consent_cookie_patches";
const WEBSITE_COOKIE_PATCH = "@website/js/http_cookie";
const DEFAULT_LOAD_ORDER = [WEBSITE_COOKIE_PATCH, PATCHES];

/**
 * ES module -> function body. Only the two forms these files use are
 * understood (`import { a, b as c } from "x";` and `export <declaration>`);
 * anything else is left in place and is a SyntaxError, reported loudly.
 */
function transform(source) {
    const exported = [];
    const body = source
        .replace(
            /^import\s*\{([^}]*)\}\s*from\s*"([^"]+)";?/gm,
            (_match, names, specifier) =>
                `const {${names.replace(/\bas\b/g, ":")}} = __require(${JSON.stringify(specifier)});`
        )
        .replace(
            /^export\s+((?:async\s+)?function\*?|const|let|class)\s+([A-Za-z_$][\w$]*)/gm,
            (_match, kind, name) => {
                exported.push(name);
                return `${kind} ${name}`;
            }
        );
    return `(function (__require, __exports) {"use strict";\n${body}\nObject.assign(__exports, {${exported.join(
        ", "
    )}});\n})`;
}

/** One realm per test case: fresh globals, fresh modules, fresh patches. */
function createRealm(modulePaths, page, testCase) {
    const context = vm.createContext({
        document: {
            get cookie() {
                return page.jar.cookie;
            },
            set cookie(value) {
                page.jar.cookie = value;
            },
            // `isAllowedCookie` takes this element as "the bar is enabled".
            getElementById: (id) => (id === "cookies-consent-essential" ? {} : null),
        },
        window: {
            get location() {
                return { hostname: page.host, protocol: page.protocol };
            },
        },
    });
    if (testCase.now) {
        vm.runInContext(`Date.now = () => ${Number(testCase.now)};`, context);
    }
    const fakes = {
        "@web/session": () => ({ session: testCase.session || {} }),
        "@website/interactions/cookies/cookies_bar": () => {
            const { cookie } = require_("@web/core/browser/cookie");
            class CookiesBar {
                constructor(el) {
                    this.el = el;
                }
                setup() {
                    // What `Popup.setup()` derives from the cookie.
                    this.popupAlreadyShown = !!cookie.get(this.el.id);
                }
            }
            return { CookiesBar };
        },
    };
    const loaded = new Map();
    function require_(specifier) {
        if (!loaded.has(specifier)) {
            const exports = {};
            loaded.set(specifier, exports);
            if (fakes[specifier]) {
                Object.assign(exports, fakes[specifier]());
            } else if (modulePaths[specifier]) {
                const filename = modulePaths[specifier];
                const factory = vm.runInContext(transform(fs.readFileSync(filename, "utf8")), context, {
                    filename,
                });
                factory(require_, exports);
            } else {
                throw new Error(`the harness does not know the module ${specifier}`);
            }
        }
        return loaded.get(specifier);
    }
    return require_;
}

function domainMatches(host, domain) {
    return host === domain || host.endsWith("." + domain);
}

class CookieStore {
    constructor({ strictIdentity = false, publicSuffixes = [] } = {}) {
        this.strictIdentity = strictIdentity;
        this.publicSuffixes = new Set(publicSuffixes);
        this.cookies = [];
        this.clock = 0;
    }

    set(host, secureOrigin, cookieString) {
        const [pair, ...attributes] = cookieString.split(";").map((part) => part.trim());
        const [name, value] = pair.split(/=(.*)/);
        const cookie = { name, value: value || "", domain: host, hostOnly: true, path: "/" };
        let maxAge = null;
        for (const attribute of attributes) {
            const [rawKey, rawValue = ""] = attribute.split(/=(.*)/);
            const key = rawKey.toLowerCase();
            if (key === "domain" && rawValue) {
                cookie.domain = rawValue.toLowerCase().replace(/^\./, "");
                cookie.hostOnly = false;
            } else if (key === "path") {
                cookie.path = rawValue;
            } else if (key === "max-age") {
                maxAge = parseInt(rawValue, 10);
            } else if (key === "samesite") {
                cookie.sameSite = rawValue;
            } else if (key === "secure") {
                cookie.secure = true;
            }
        }
        if (!cookie.hostOnly) {
            if (this.publicSuffixes.has(cookie.domain) || !domainMatches(host, cookie.domain)) {
                return;
            }
        }
        if (cookie.secure && !secureOrigin) {
            return;
        }
        const sameIdentity = (other) =>
            other.name === cookie.name &&
            other.domain === cookie.domain &&
            other.path === cookie.path &&
            (this.strictIdentity || other.hostOnly === cookie.hostOnly);
        const previous = this.cookies.find(sameIdentity);
        this.cookies = this.cookies.filter((other) => !sameIdentity(other));
        if (maxAge !== null && maxAge <= 0) {
            return;
        }
        cookie.maxAge = maxAge;
        cookie.created = previous ? previous.created : ++this.clock;
        this.cookies.push(cookie);
    }

    visibleFrom(host) {
        return this.cookies
            .filter((cookie) =>
                cookie.hostOnly ? cookie.domain === host : domainMatches(host, cookie.domain)
            )
            .sort((a, b) => a.created - b.created);
    }

    jar(host, secureOrigin) {
        const store = this;
        return {
            get cookie() {
                return store
                    .visibleFrom(host)
                    .map((cookie) => `${cookie.name}=${cookie.value}`)
                    .join("; ");
            },
            set cookie(cookieString) {
                store.set(host, secureOrigin, cookieString);
            },
        };
    }

    dump() {
        return this.cookies
            .map(({ name, value, domain, hostOnly, path, maxAge, sameSite, secure }) => ({
                name,
                value,
                domain,
                hostOnly,
                path,
                maxAge,
                sameSite: sameSite || null,
                secure: Boolean(secure),
            }))
            .sort((a, b) => Number(a.hostOnly) - Number(b.hostOnly));
    }
}

const BAR_ELEMENT = {
    id: "website_cookies_bar",
    querySelector: (selector) =>
        selector === ".modal" ? { dataset: { consentsDuration: "999" } } : null,
};

function runCase(modulePaths, testCase) {
    const store = new CookieStore(testCase);
    const page = { host: "", protocol: "https:", jar: null };
    const require_ = createRealm(modulePaths, page, testCase);
    for (const specifier of testCase.loadOrder || DEFAULT_LOAD_ORDER) {
        require_(specifier);
    }
    const { cookie } = require_("@web/core/browser/cookie");
    const { CookiesBar } = require_("@website/interactions/cookies/cookies_bar");
    const helpers = require_(HELPERS);
    const results = [];
    for (const step of testCase.steps) {
        page.host = step.host || "";
        page.protocol = step.protocol || "https:";
        page.jar = store.jar(page.host, page.protocol === "https:");
        const helperParams = {
            domain: step.domain,
            secure: page.protocol === "https:",
            ttl: step.ttl,
            now: step.now,
            value: step.value,
        };
        const ops = {
            // A cookie exactly as something else (core, another host) wrote it.
            raw: () => {
                page.jar.cookie = step.cookie;
                return null;
            },
            read: () => page.jar.cookie,
            // Through the shipped patches, as the website frontend does.
            set: () => {
                cookie.set(step.key || helpers.CONSENT_COOKIE, step.value, step.ttl, step.type);
                return null;
            },
            delete: () => {
                cookie.delete(step.key || helpers.CONSENT_COOKIE);
                return null;
            },
            get: () => cookie.get(step.key || helpers.CONSENT_COOKIE) ?? null,
            setup: () => {
                const bar = new CookiesBar(BAR_ELEMENT);
                bar.setup();
                return bar.popupAlreadyShown;
            },
            // The pure helpers, for what only their return value tells.
            guard: () => helpers.sharedDomainForHost(step.host, step.configured),
            normalize: () => helpers.normalizeSharedDomain(step.value),
            resolve: () => helpers.resolveConsent(step.values),
            promoteHelper: () => helpers.promoteHostOnlyConsent(page.jar, helperParams),
            writeHelper: () => helpers.writeSharedConsent(page.jar, helperParams),
        };
        if (!ops[step.op]) {
            throw new Error(`unknown op ${step.op}`);
        }
        results.push(ops[step.op]());
    }
    const { CONSENT_COOKIE, DEFAULT_TTL } = helpers;
    return { results, cookies: store.dump(), constants: { CONSENT_COOKIE, DEFAULT_TTL } };
}

function main() {
    const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
    const cases = {};
    for (const testCase of input.cases) {
        cases[testCase.name] = runCase(input.modules, testCase);
    }
    return { cases };
}

try {
    process.stdout.write(JSON.stringify(main()));
} catch (error) {
    process.stdout.write(JSON.stringify({ harnessError: String(error && error.stack) }));
}
