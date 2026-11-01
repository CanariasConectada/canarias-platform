/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";

/**
 * A walk-in community guest is asked who they are before the conversation
 * opens, and the conversation carries the name they typed.
 */
registry.category("web_tour.tours").add("website_pwa_chat_support_request_discuss_guest", {
    steps: () => [
        {
            content: "Ask for support from the sidebar",
            trigger: ".o_cc_support_request_button",
            run: "click",
        },
        {
            content: "An empty name is not accepted",
            trigger: ".modal .o_cc_support_name_confirm",
            run: "click",
        },
        {
            content: "The dialog says so and stays open",
            trigger: ".modal .o_cc_support_name.is-invalid",
        },
        {
            content: "Type a name",
            trigger: ".modal .o_cc_support_name",
            run: "edit Carmen la del kiosco",
        },
        {
            content: "Confirm",
            trigger: ".modal .o_cc_support_name_confirm",
            run: "click",
        },
        {
            content: "The conversation is open under the typed name",
            trigger: ".o-mail-DiscussSidebar-item.o-active:contains(Carmen la del kiosco)",
        },
    ],
});
