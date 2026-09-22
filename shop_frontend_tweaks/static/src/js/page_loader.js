/**
 * Slim top progress bar shown while the browser fetches the next page.
 *
 * The felt delay lives between the click and the first byte of the next
 * document, before any unload event fires, so the trigger has to be the
 * click itself. Every guard below exists to avoid lying to the user:
 * a bar that shows up when no navigation happens is worse than none.
 */
(function () {
    "use strict";

    const BAR_ID = "cc_page_loader";
    const SAFETY_TIMEOUT = 8000;
    let bar = null;
    let crawlTimer = null;
    let safetyTimer = null;

    function ensureBar() {
        if (!bar) {
            bar = document.createElement("div");
            bar.id = BAR_ID;
            bar.setAttribute("role", "progressbar");
            bar.setAttribute("aria-hidden", "true");
            document.body.appendChild(bar);
        }
        return bar;
    }

    function show() {
        const el = ensureBar();
        clearTimeout(crawlTimer);
        clearTimeout(safetyTimer);
        el.style.transition = "none";
        el.style.width = "0";
        el.classList.add("cc-loading");
        // Force a reflow so the width reset lands before the crawl starts.
        void el.offsetWidth;
        el.style.transition = "";
        el.style.width = "70%";
        crawlTimer = setTimeout(() => {
            el.style.width = "90%";
        }, 1500);
        // If nothing actually navigated (dialog cancelled, JS took over
        // later, download prompt), retract instead of crawling forever.
        safetyTimer = setTimeout(hide, SAFETY_TIMEOUT);
    }

    function hide() {
        clearTimeout(crawlTimer);
        clearTimeout(safetyTimer);
        if (bar) {
            bar.classList.remove("cc-loading");
            bar.style.width = "0";
        }
    }

    function isPlainLeftClick(ev) {
        return (
            ev.button === 0 &&
            !ev.metaKey &&
            !ev.ctrlKey &&
            !ev.shiftKey &&
            !ev.altKey
        );
    }

    function navigatesAway(anchor) {
        if (!anchor || anchor.hasAttribute("download")) {
            return false;
        }
        if (anchor.target && anchor.target !== "_self") {
            return false;
        }
        const href = anchor.getAttribute("href") || "";
        if (!href || href.startsWith("#")) {
            return false;
        }
        if (/^(javascript|mailto|tel|sms):/i.test(href)) {
            return false;
        }
        let url;
        try {
            url = new URL(anchor.href, window.location.href);
        } catch {
            return false;
        }
        if (url.origin !== window.location.origin) {
            return false;
        }
        // Same page, different fragment: no fetch happens.
        return !(
            url.pathname === window.location.pathname &&
            url.search === window.location.search &&
            url.hash
        );
    }

    document.addEventListener("click", (ev) => {
        if (!isPlainLeftClick(ev)) {
            return;
        }
        const anchor = ev.target.closest && ev.target.closest("a[href]");
        if (!navigatesAway(anchor)) {
            return;
        }
        // Let same-tick handlers cancel the navigation before we react.
        setTimeout(() => {
            if (!ev.defaultPrevented) {
                show();
            }
        }, 0);
    });

    document.addEventListener("submit", (ev) => {
        const form = ev.target;
        if (form.target && form.target !== "_self") {
            return;
        }
        setTimeout(() => {
            if (!ev.defaultPrevented) {
                show();
            }
        }, 0);
    });

    // Back-forward cache restores skip the load event; without this the
    // bar from the outgoing navigation would still be on screen.
    window.addEventListener("pageshow", hide);
})();
