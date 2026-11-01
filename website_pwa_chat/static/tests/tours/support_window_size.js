/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";

/**
 * The floating support window is big enough to read, on a desktop and on a
 * phone, the page inside it does not scroll on its own, and it is a support
 * chat and nothing else: no publishing, no review, no channel list.
 *
 * Sizes are asserted in rem so the check does not depend on the theme's root
 * font size. The browser size comes from the HttpCase class that runs it.
 */
function rem() {
    return parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
}

function checkWindowSize() {
    const box = document.querySelector(".o_cc_chat_window").getBoundingClientRect();
    const unit = rem();
    const viewportW = document.documentElement.clientWidth;
    const viewportH = window.innerHeight;
    if (box.top < 0 || box.bottom > viewportH || box.left < 0 || box.right > viewportW) {
        throw new Error(`The support window leaves the viewport: ${JSON.stringify(box)}`);
    }
    if (viewportW < 576) {
        // A phone: nearly the whole screen.
        if (box.width < viewportW - 2 * unit || box.height < viewportH - 6 * unit) {
            throw new Error(
                `The support window is not near full-screen on a phone: ` +
                    `${box.width}x${box.height} in ${viewportW}x${viewportH}`
            );
        }
        return;
    }
    const expectedH = Math.min(42 * unit, viewportH - 5.5 * unit);
    const expectedW = Math.min(26 * unit, viewportW - 2 * unit);
    if (Math.abs(box.height - expectedH) > 1 || Math.abs(box.width - expectedW) > 1) {
        throw new Error(
            `The support window is ${box.width}x${box.height}, ` +
                `expected ${expectedW}x${expectedH}`
        );
    }
}

function checkFrameDoesNotScroll() {
    const frame = document.querySelector(".o_cc_chat_window_frame");
    const doc = frame.contentDocument;
    const scroller = doc.scrollingElement;
    if (scroller.scrollHeight > scroller.clientHeight + 1) {
        throw new Error(
            `The page inside the support window scrolls: ` +
                `${scroller.scrollHeight} > ${scroller.clientHeight}`
        );
    }
    const composer = doc.querySelector(".o_cc_chat_composer").getBoundingClientRect();
    if (composer.bottom > frame.clientHeight + 1) {
        const page = doc.querySelector(".o_cc_chat_framed");
        const parts = [...page.children].map(
            (el) => `${el.className}:${Math.round(el.getBoundingClientRect().height)}`
        );
        const chain = [];
        for (let el = page; el; el = el.parentElement) {
            const r = el.getBoundingClientRect();
            chain.push(`${el.tagName}#${el.id}.${el.className}@${Math.round(r.top)}+${Math.round(r.height)}`);
        }
        throw new Error(
            `The composer is clipped below the support window ` +
                `(bottom ${composer.bottom} > ${frame.clientHeight}): ` +
                `${parts.join(" | ")} || ${chain.join(" < ")}`
        );
    }
}

/**
 * The site's cookie bar is a Bootstrap modal (1055) pinned to the bottom of
 * the page. While the window is open it must sit UNDER the window -- the
 * composer is what it used to cover -- and it must be the only modal that
 * does: the window itself stays below Bootstrap's modal layer, so any real
 * dialog still wins. Once the window closes the bar gets its place back.
 *
 * The tour engine refuses actions on anything outside a visible modal, so
 * "usable" is asserted the way a finger would find it: the point at the
 * centre of the composer belongs to the window's frame, not to the bar.
 */
function cookieBarModal() {
    return document.querySelector("#website_cookies_bar .modal");
}

function checkCookieBarUnderWindow() {
    const bar = cookieBarModal();
    const windowEl = document.querySelector(".o_cc_chat_window");
    const frame = windowEl.querySelector(".o_cc_chat_window_frame");
    const barZ = parseInt(getComputedStyle(bar).zIndex, 10);
    const windowZ = parseInt(getComputedStyle(windowEl).zIndex, 10);
    if (!(barZ < windowZ)) {
        throw new Error(`Cookie bar (${barZ}) is not below the window (${windowZ})`);
    }
    if (!(windowZ < 1055)) {
        throw new Error(`The window (${windowZ}) climbed over Bootstrap's modal layer`);
    }
    const composer = frame.contentDocument
        .querySelector(".o_cc_chat_composer")
        .getBoundingClientRect();
    const box = frame.getBoundingClientRect();
    const x = box.left + composer.left + composer.width / 2;
    const y = box.top + composer.top + composer.height / 2;
    const hit = document.elementFromPoint(x, y);
    if (hit !== frame) {
        throw new Error(
            `The composer is covered at (${x}, ${y}) by ${hit && hit.outerHTML.slice(0, 120)}`
        );
    }
}

function checkCookieBarRestored() {
    const barZ = parseInt(getComputedStyle(cookieBarModal()).zIndex, 10);
    if (barZ < 1055) {
        throw new Error(`The cookie bar stayed lowered (${barZ}) after closing`);
    }
}

// Triggers start with "body" where they act: the cookie bar is a visible
// modal on this page, and the tour engine exempts only such triggers from
// its "do not act below a modal" rule.
registry.category("web_tour.tours").add("website_pwa_chat_support_window_size", {
    steps: () => [
        {
            content: "The site's cookie bar is up, waiting for an answer",
            trigger: "body #website_cookies_bar .modal.show",
        },
        {
            content: "Open the support window",
            trigger: "body .o_cc_chat_fab",
            run: "click",
        },
        {
            content: "The window is open and sized to be read",
            trigger: "body .o_cc_chat_window:not(.d-none)",
            run: checkWindowSize,
        },
        {
            content: "The conversation page has loaded inside it",
            trigger: ":iframe .o_cc_chat_framed .o_cc_chat_composer",
        },
        {
            content: "Nothing inside the window scrolls but the conversation",
            trigger: "body .o_cc_chat_window:not(.d-none)",
            run: checkFrameDoesNotScroll,
        },
        {
            content: "The cookie bar, and only it, sits under the open window",
            trigger: "body.o_cc_support_open .o_cc_chat_window:not(.d-none)",
            run: checkCookieBarUnderWindow,
        },
        {
            content: "Close the window",
            trigger: "body .o_cc_chat_window_close",
            run: "click",
        },
        {
            content: "The cookie bar is back on top",
            trigger: "body:not(.o_cc_support_open) .o_cc_chat_window.d-none:not(:visible)",
            run: checkCookieBarRestored,
        },
    ],
});

/**
 * Client feedback 2026-09-29: "support mixed with messages to publish".
 * Support publishes nothing, so nothing in the window may talk about review,
 * publishing, registering to skip a queue, or the community channels. Checked
 * on what is RENDERED and visible, which is what the visitor reads.
 */
function checkNoCommunityUi() {
    const doc = document.querySelector(".o_cc_chat_window_frame").contentDocument;
    const forbidden = [
        ".o_cc_chat_pending_zone",
        ".o_cc_chat_pending",
        ".o_cc_chat_hint",
        ".o_cc_chat_rejected",
        ".o_cc_chat_identify_signup",
        ".o_cc_chat_channels",
        "a[href*='/web/signup']",
        "a[href$='/chat']",
        "h1",
    ];
    for (const selector of forbidden) {
        if (doc.querySelector(selector)) {
            throw new Error(`The support window shows ${selector}`);
        }
    }
    const text = doc.body.innerText.toLowerCase();
    for (const word of ["revisión", "publica", "review", "publish"]) {
        if (text.includes(word)) {
            throw new Error(`The support window talks about "${word}": ${text}`);
        }
    }
    for (const selector of ["#website_cookies_bar", ".o_frontend_to_backend_nav"]) {
        const el = doc.querySelector(selector);
        if (el && el.getClientRects().length) {
            throw new Error(`The page chrome ${selector} is visible inside the window`);
        }
    }
    if (doc.querySelectorAll(".o_cc_chat_composer").length !== 1) {
        throw new Error("The support window must have exactly one composer");
    }
}

function supportSimpleSteps({anonymous}) {
    const body = "Hola, no encuentro cómo cambiar el horario";
    return [
        {
            content: "Open the support window",
            trigger: ".o_cc_chat_fab",
            run: "click",
        },
        {
            content: "The support page has loaded inside it",
            trigger: ":iframe .o_cc_chat_framed .o_cc_chat_composer",
        },
        {
            content: "Nobody has written yet: no name is asked",
            trigger: ":iframe .o_cc_chat_framed:not(:has(.o_cc_chat_identify:not(.d-none)))",
        },
        {
            content: "Only the conversation and the composer",
            trigger: ".o_cc_chat_window:not(.d-none)",
            run: checkNoCommunityUi,
        },
        {
            content: "Write the question",
            trigger: ":iframe .o_cc_chat_input",
            run: `edit ${body}`,
        },
        {
            content: "Send it",
            trigger: ":iframe .o_cc_chat_send",
            run: "click",
        },
        {
            content: "It is in the conversation straight away, never held",
            trigger: `:iframe .o_cc_chat_message:contains(${body})`,
        },
        anonymous
            ? {
                  content: "Now, and only now, the one-line name question",
                  trigger: ":iframe .o_cc_chat_identify:not(.d-none) input[name=name]",
              }
            : {
                  content: "A logged-in user is never asked for a name",
                  trigger: ":iframe .o_cc_chat_framed:not(:has(.o_cc_chat_identify))",
              },
        {
            content: "Still nothing of the community after the first message",
            trigger: ".o_cc_chat_window:not(.d-none)",
            run: checkNoCommunityUi,
        },
        {
            content: "And still nothing scrolls but the conversation",
            trigger: ".o_cc_chat_window:not(.d-none)",
            run: checkFrameDoesNotScroll,
        },
        ...(anonymous
            ? [
                  {
                      content: "Give a name",
                      trigger: ":iframe .o_cc_chat_identify input[name=name]",
                      run: "edit Lucía",
                  },
                  {
                      content: "Save it in place",
                      trigger: ":iframe .o_cc_chat_identify button[type=submit]",
                      run: "click",
                  },
                  {
                      content: "Thanked in place, and the question is gone",
                      trigger: ":iframe .o_cc_chat_identified:contains(Lucía)",
                  },
                  {
                      content: "No form left behind",
                      trigger: ":iframe .o_cc_chat_framed:not(:has(.o_cc_chat_identify))",
                  },
                  {
                      content: "The conversation survived the save",
                      trigger: `:iframe .o_cc_chat_message:contains(${body})`,
                  },
              ]
            : []),
    ];
}

registry.category("web_tour.tours").add("website_pwa_chat_support_simple_anonymous", {
    steps: () => supportSimpleSteps({anonymous: true}),
});

registry.category("web_tour.tours").add("website_pwa_chat_support_simple_user", {
    steps: () => supportSimpleSteps({anonymous: false}),
});
