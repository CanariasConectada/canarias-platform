/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";

/**
 * A merchant asks for support from the Discuss sidebar and lands in the
 * conversation, named after them.
 */
registry.category("web_tour.tours").add("website_pwa_chat_support_request_discuss", {
    steps: () => [
        {
            content: "Ask for support from the sidebar",
            trigger: ".o_cc_support_request_button",
            run: "click",
        },
        {
            content: "The conversation is open and carries the merchant's name",
            trigger: ".o-mail-DiscussSidebar-item.o-active:contains(Ferretería Las Canteras)",
        },
        {
            content: "It can be written in",
            trigger: ".o-mail-Composer-input",
        },
    ],
});
