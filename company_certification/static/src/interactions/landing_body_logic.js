// Decisions behind the certification landing body, kept apart from the DOM.
// This file imports NOTHING on purpose: `tests/landing_body_harness.js` runs
// these exact bytes in `node`, so what is tested is what is served. The
// interaction in `landing_body.js` only reads the page, asks here what to do,
// and does it.

export const CAROUSEL_INTERVAL = 5000;

/**
 * Options of the Bootstrap carousel of a body.
 *
 * `ride` is set explicitly because nothing in the markup can say it: the
 * field sanitizer strips data-bs-ride and data-bs-interval. A visitor who
 * asked for reduced motion gets a carousel that only moves when told to.
 *
 * @param {boolean} prefersReducedMotion
 * @returns {{ride: (string|boolean), interval: number, rideAttribute: string}}
 */
export function carouselOptions(prefersReducedMotion) {
    const ride = prefersReducedMotion ? false : "carousel";
    return { ride, interval: CAROUSEL_INTERVAL, rideAttribute: String(ride) };
}

/**
 * Which panels of an accordion to close when one opens: every other panel
 * that is open, which is what data-bs-parent did before the sanitizer removed
 * it.
 *
 * @param {{id: string, shown: boolean}[]} panels the accordion's panels
 * @param {string} openingId the panel being opened
 * @returns {string[]} ids to close
 */
export function panelsToClose(panels, openingId) {
    return panels
        .filter((panel) => panel.shown && panel.id !== openingId)
        .map((panel) => panel.id);
}

/**
 * What a key press on a trigger means.
 *
 * The triggers are links because the sanitizer strips <button>, and a link
 * only answers Enter: Space scrolls the page instead. A link with an href
 * keeps its native Enter; anything else (no href) gets Enter from here too.
 *
 * @param {string} key KeyboardEvent.key
 * @param {{hasHref: boolean, modified?: boolean}} trigger
 * @returns {("activate"|null)} "activate": prevent the default and click
 */
export function keyAction(key, { hasHref, modified = false }) {
    if (modified) {
        return null;
    }
    if (key === " " || key === "Spacebar" || key === "Space") {
        return "activate";
    }
    if (key === "Enter" && !hasHref) {
        return "activate";
    }
    return null;
}

/**
 * The id a trigger points at, from an in-page href ("#panel", or a full URL
 * ending in "#panel" as the editor sometimes stores it).
 *
 * @param {(string|null|undefined)} href
 * @returns {(string|null)}
 */
export function targetIdFromHref(href) {
    const hash = (href || "").split("#")[1];
    return hash ? decodeURIComponent(hash) : null;
}

/**
 * What kind of widget a trigger drives, from the only things that survive the
 * sanitizer: its classes and data-bs-toggle.
 *
 * @param {{classes: string[], toggle: (string|null|undefined)}} trigger
 * @returns {("collapse"|"modal"|"carousel-prev"|"carousel-next"|"indicator"|"close"|null)}
 */
export function triggerKind({ classes, toggle, inIndicators = false }) {
    if (toggle === "collapse" || toggle === "modal") {
        return toggle;
    }
    if (classes.includes("carousel-control-prev")) {
        return "carousel-prev";
    }
    if (classes.includes("carousel-control-next")) {
        return "carousel-next";
    }
    if (classes.includes("btn-close")) {
        return "close";
    }
    return inIndicators ? "indicator" : null;
}

/**
 * The ARIA a trigger must carry, all of it stripped by the sanitizer and so
 * put back at start. `expanded` only means something for a collapse.
 *
 * @param {string} kind a value of triggerKind()
 * @param {{targetId?: (string|null), expanded?: boolean, hasHref?: boolean,
 *          label?: (string|null)}} state
 * @returns {Object<string, string>} attribute name -> value
 */
export function ariaFor(kind, { targetId = null, expanded = false, hasHref = true, label = null } = {}) {
    if (!kind) {
        return {};
    }
    const attrs = { role: "button" };
    if (!hasHref) {
        attrs.tabindex = "0";
    }
    if (kind === "collapse") {
        attrs["aria-expanded"] = expanded ? "true" : "false";
    }
    if ((kind === "collapse" || kind === "modal") && targetId) {
        attrs["aria-controls"] = targetId;
    }
    if (label) {
        attrs["aria-label"] = label;
    }
    return attrs;
}

/**
 * Accessible name of a carousel indicator: its slide's caption, else its
 * position. Content-derived on purpose, so it needs no translation.
 *
 * @param {(string|null|undefined)} caption
 * @param {number} index zero-based
 * @returns {string}
 */
export function indicatorLabel(caption, index) {
    const text = (caption || "").replace(/\s+/g, " ").trim();
    return text || String(index + 1);
}

/**
 * Which indicator is the active one after a slide: Bootstrap follows
 * data-bs-slide-to, which is gone, so the position is used.
 *
 * @param {number} count
 * @param {number} activeIndex
 * @returns {boolean[]}
 */
export function indicatorStates(count, activeIndex) {
    return Array.from({ length: count }, (_, position) => position === activeIndex);
}
