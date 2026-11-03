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
        // Posting still works with the guest member rules in place.
        {trigger: ".o-mail-Composer-input", run: "edit Hello from the DCM guest"},
        {trigger: ".o-mail-Composer-input", run: "press Enter"},
        {trigger: ".o-mail-Message-body:contains('Hello from the DCM guest')"},
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

/**
 * Throw unless the Discuss root spans the whole action container (±2px).
 * Regression of 19.0.1.4.0: wrapped in a flex ROW, core's Discuss root
 * shrank to its content and left an empty band on the right.
 */
function assertDiscussFullWidth(label) {
    const container = document.querySelector(".o_action_manager");
    const root = document.querySelector(".o_dc_discuss_body > *");
    if (!container || !root) {
        throw new Error(`${label}: action container or Discuss root not found`);
    }
    const expected = container.getBoundingClientRect().width;
    const actual = root.getBoundingClientRect().width;
    if (Math.abs(expected - actual) > 2) {
        throw new Error(
            `${label}: Discuss root is ${actual}px wide, the action container ${expected}px`
        );
    }
}

/**
 * Discuss takes the whole width with the banner shown and hidden, and the
 * member panel still opens and closes for an administrator.
 */
registry.category("web_tour.tours").add("discuss_community_layout", {
    steps: () => [
        {
            trigger: ".o-mail-DiscussContent-threadName[title='DCM Short Thread']",
        },
        {trigger: ".o-mail-Message-body:contains('Short thread')"},
        {
            trigger: ".o_dc_notification_banner",
            run: () => assertDiscussFullWidth("banner visible"),
        },
        {trigger: ".o_dc_notification_banner_dismiss", run: "click"},
        {
            trigger: "body:not(:has(.o_dc_notification_banner))",
            run: () => assertDiscussFullWidth("banner hidden"),
        },
        // Discuss auto-opens the member panel for channels (core's own
        // discuss.invite_by_email tour waits for it the same way).
        {trigger: ".o-discuss-ChannelMemberList"},
        {trigger: `${HEADER} button[name='member-list']`, run: "click"},
        {
            trigger: ".o-mail-DiscussContent:not(:has(.o-discuss-ChannelMemberList))",
            run: () => assertDiscussFullWidth("member panel closed"),
        },
        {trigger: `${HEADER} button[name='member-list']`, run: "click"},
        {
            trigger: ".o-discuss-ChannelMemberList",
            run: () => assertDiscussFullWidth("member panel open"),
        },
    ],
});
