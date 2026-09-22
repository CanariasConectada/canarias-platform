/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {fields} from "@mail/core/common/record";
import {Thread} from "@mail/core/common/thread_model";
import {DiscussApp} from "@mail/core/public_web/discuss_app_model";
import {DiscussAppCategory} from "@mail/discuss/core/public_web/discuss_app_category_model";
import {compareDatetime} from "@mail/utils/common/misc";
import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

/**
 * One collapsible "Soporte" row in the Discuss sidebar.
 *
 * Support conversations are `group` channels, so core files every one of
 * them under "Direct messages" -- with a platform of 218 shops feeding the
 * queue, that list drowns the agents' own conversations. This gives them a
 * category of their own, foldable like any other; the open/closed state
 * persists per browser through the category model's own localStorage
 * fallback (no `serverStateKey`, so nothing to store server side).
 *
 * `hideWhenEmpty`: an agent with no support conversation pinned should not
 * see an empty drawer.
 */
patch(DiscussApp.prototype, {
    setup() {
        super.setup(...arguments);
        this.ccSupport = fields.One("DiscussAppCategory", {
            compute() {
                return {
                    canView: false,
                    extraClass: "o-mail-DiscussSidebarCategory-chat",
                    icon: "fa fa-life-ring",
                    id: "cc_support",
                    name: _t("Soporte"),
                    // After Channels (10) and before Direct messages (30):
                    // answering visitors is these users' job, chatting with
                    // colleagues is not.
                    sequence: 20,
                    hideWhenEmpty: true,
                };
            },
            eager: true,
        });
    },
});

patch(Thread.prototype, {
    _computeDiscussAppCategory() {
        if (this.is_support_channel && !this.parent_channel_id) {
            return this.store.discuss.ccSupport;
        }
        return super._computeDiscussAppCategory(...arguments);
    },
});

patch(DiscussAppCategory.prototype, {
    sortThreads(t1, t2) {
        if (this.id === "cc_support") {
            // Freshest conversation first, same as Direct messages: the top
            // of the drawer is the visitor waiting the shortest time.
            return compareDatetime(t2.lastInterestDt, t1.lastInterestDt) || t2.id - t1.id;
        }
        return super.sortThreads(...arguments);
    },
});
