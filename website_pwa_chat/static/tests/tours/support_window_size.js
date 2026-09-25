/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";

/**
 * The floating support window is big enough to read, on a desktop and on a
 * phone, and the page inside it does not scroll on its own.
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

registry.category("web_tour.tours").add("website_pwa_chat_support_window_size", {
    steps: () => [
        {
            content: "Open the support window",
            trigger: ".o_cc_chat_fab",
            run: "click",
        },
        {
            content: "The window is open and sized to be read",
            trigger: ".o_cc_chat_window:not(.d-none)",
            run: checkWindowSize,
        },
        {
            content: "The conversation page has loaded inside it",
            trigger: ":iframe .o_cc_chat_framed .o_cc_chat_composer",
        },
        {
            content: "Nothing inside the window scrolls but the conversation",
            trigger: ".o_cc_chat_window:not(.d-none)",
            run: checkFrameDoesNotScroll,
        },
    ],
});
