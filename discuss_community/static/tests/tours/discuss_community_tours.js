/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";

const HEADER = ".o-mail-DiscussContent-header";

/**
 * A community guest lands in the community channel, with no calls, no
 * member list, no header actions and no "Start a meeting" button, and is
 * asked to turn on notifications.
 */
registry.category("web_tour.tours").add("discuss_community_guest_profile", {
    steps: () => [
        {
            trigger: ".o-mail-DiscussContent-threadName[title='Canarias Conectada']",
        },
        {trigger: ".o_dc_notification_banner"},
        {trigger: ".o-mail-Composer-input"},
        {trigger: `${HEADER}:not(:has(button[name='call']))`},
        {trigger: `${HEADER}:not(:has(button[name='camera-call']))`},
        {trigger: `${HEADER}:not(:has(button[name='member-list']))`},
        {trigger: `${HEADER}:not(:has(.o-mail-ActionList-button))`},
        {trigger: ".o-mail-DiscussContent:not(:has(.o-discuss-ChannelMemberList))"},
        {trigger: ".o-mail-DiscussSearch:not(:has(button[data-hotkey='m']))"},
        {trigger: ".o_dc_notification_banner_dismiss", run: "click"},
        {trigger: "body:not(:has(.o_dc_notification_banner))"},
    ],
});

/**
 * An ordinary internal user keeps the stock header (calls, member list) and
 * also gets the notifications banner.
 */
registry.category("web_tour.tours").add("discuss_community_employee_profile", {
    steps: () => [
        {
            trigger: ".o-mail-DiscussContent-threadName[title='DCM Open Channel']",
        },
        {trigger: ".o_dc_notification_banner"},
        {trigger: `${HEADER} button[name='call']`},
        {trigger: `${HEADER} button[name='member-list']`},
    ],
});
