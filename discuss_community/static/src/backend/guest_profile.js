/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {DiscussClientAction} from "@mail/core/public_web/discuss_client_action";
import {DiscussContent} from "@mail/core/public_web/discuss_content";
import {DiscussSearch} from "@mail/core/public_web/discuss_search";
import {ThreadAction} from "@mail/core/common/thread_actions";
import {patch} from "@web/core/utils/patch";
import {session} from "@web/session";

/**
 * The Discuss profile of a community guest.
 *
 * A guest is a throwaway internal account whose whole backend is Discuss.
 * The server tells the client who is a guest (`session_info`); these patches
 * only trim the UI. What the guest may read or join is enforced server side
 * by the record rules of the module, never here.
 */

export function isCommunityGuest() {
    return Boolean(session.is_community_guest);
}

/** Thread actions a guest never gets, wherever they are rendered. */
export const GUEST_HIDDEN_ACTIONS = new Set([
    "call",
    "camera-call",
    "call-settings",
    "member-list",
    "invite-people",
]);

/**
 * Thread actions a guest keeps in a thread header (Discuss content or chat
 * window). Everything else on the right side of the header is hidden: the
 * guest needs to read and write, and to fold or close a chat window.
 */
export const GUEST_HEADER_ACTIONS = new Set(["fold-chat-window", "close", "expand-discuss"]);

patch(ThreadAction.prototype, {
    _condition({action, owner}) {
        if (isCommunityGuest()) {
            if (GUEST_HIDDEN_ACTIONS.has(action.id)) {
                return false;
            }
            // The hover actions of a sidebar row (mark as read, leave, ...)
            // are not header buttons: core decides those.
            if (!owner.isDiscussSidebarChannelActions && !GUEST_HEADER_ACTIONS.has(action.id)) {
                return false;
            }
        }
        return super._condition(...arguments);
    },
});

patch(DiscussContent.prototype, {
    actionPanelAutoOpenFn() {
        // Core opens the member list panel by default on wide screens.
        if (isCommunityGuest()) {
            return;
        }
        return super.actionPanelAutoOpenFn(...arguments);
    },
});

patch(DiscussSearch.prototype, {
    setup() {
        super.setup(...arguments);
        // Read by the template: no "Start a meeting" button for guests.
        this.isCommunityGuest = isCommunityGuest();
    },
});

/**
 * On their first visit to Discuss after loading the web client, guests land
 * in the community channel instead of the last conversation (or OdooBot, or
 * an empty screen). An explicit `active_id` in the action or the URL still
 * wins, and so does navigating afterwards.
 */
let guestLandingDone = false;

export function resetGuestLanding() {
    guestLandingDone = false;
}

patch(DiscussClientAction.prototype, {
    getActiveId(props) {
        if (!guestLandingDone && isCommunityGuest()) {
            guestLandingDone = true;
            const explicit = props.action.context.active_id ?? props.action.params?.active_id;
            const channelId = session.community_default_channel_id;
            if (!explicit && channelId && !this.store.discuss.thread) {
                return `discuss.channel_${channelId}`;
            }
        }
        return super.getActiveId(...arguments);
    },
});
