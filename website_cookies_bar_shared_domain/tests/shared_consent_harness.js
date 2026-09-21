/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Runs the SHIPPED `static/src/js/shared_consent_cookie.js` in `node:vm`
 * against an emulated browser cookie store, so the helpers are judged by what
 * a browser would end up storing and not by the strings they build.
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
 * Usage:  node shared_consent_harness.js <shared_consent_cookie.js> <input.json>
 * stdout: a single JSON object. The assertions all live in Python.
 */
"use strict";

const fs = require("fs");
const vm = require("vm");

const PROBE = `
globalThis.__api = {
    CONSENT_COOKIE,
    DEFAULT_TTL,
    normalizeSharedDomain,
    sharedDomainForHost,
    readAllValues,
    isConsentValue,
    buildConsentCookie,
    writeSharedConsent,
    promoteHostOnlyConsent,
};
`;

function loadApi(sourcePath) {
    // The file has no imports; dropping the `export` keyword is all it takes
    // to evaluate it as a classic script.
    const source = fs.readFileSync(sourcePath, "utf8").replace(/^export\s+/gm, "");
    const context = vm.createContext({ JSON, Number, Math, Date, Boolean, Set });
    vm.runInContext(source + PROBE, context, { filename: sourcePath });
    return context.__api;
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

function runCase(api, testCase) {
    const store = new CookieStore(testCase);
    const results = [];
    for (const step of testCase.steps) {
        const secureOrigin = step.protocol !== "http:";
        const jar = store.jar(step.host, secureOrigin);
        if (step.op === "raw") {
            // A cookie exactly as something else (core, another host) wrote it.
            jar.cookie = step.cookie;
            results.push(null);
        } else if (step.op === "guard") {
            results.push(api.sharedDomainForHost(step.host, step.configured));
        } else if (step.op === "normalize") {
            results.push(api.normalizeSharedDomain(step.value));
        } else if (step.op === "read") {
            results.push(jar.cookie);
        } else if (step.op === "write" || step.op === "promote") {
            // What consent_cookie_patches.js does: guard first, helper second.
            const domain = api.sharedDomainForHost(step.host, step.configured);
            if (!domain) {
                results.push("guarded");
            } else if (step.op === "write") {
                results.push(
                    api.writeSharedConsent(jar, {
                        value: step.value,
                        ttl: step.ttl,
                        domain,
                        secure: secureOrigin,
                    })
                );
            } else {
                results.push(
                    api.promoteHostOnlyConsent(jar, {
                        domain,
                        secure: secureOrigin,
                        ttl: step.ttl,
                        now: step.now,
                    })
                );
            }
        } else {
            throw new Error(`unknown op ${step.op}`);
        }
    }
    return { name: testCase.name, results, cookies: store.dump() };
}

function main() {
    const [sourcePath, inputPath] = process.argv.slice(2);
    const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
    const api = loadApi(sourcePath);
    const cases = {};
    for (const testCase of input.cases) {
        cases[testCase.name] = runCase(api, testCase);
    }
    return { constants: { cookie: api.CONSENT_COOKIE, defaultTtl: api.DEFAULT_TTL }, cases };
}

try {
    process.stdout.write(JSON.stringify(main()));
} catch (error) {
    process.stdout.write(JSON.stringify({ harnessError: String(error && error.stack) }));
}
