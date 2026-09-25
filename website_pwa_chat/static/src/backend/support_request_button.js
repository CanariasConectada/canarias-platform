/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {discussSidebarItemsRegistry} from "@mail/core/public_web/discuss_sidebar";
import {Component, useState} from "@odoo/owl";
import {rpc} from "@web/core/network/rpc";
import {useService} from "@web/core/utils/hooks";
import {session} from "@web/session";
import {SupportNameDialog} from "./support_name_dialog";

/**
 * "Request support", at the top of the Discuss sidebar.
 *
 * The website has had a support button since 19.0.2.0.0, but merchants and
 * walk-in community guests live in the backend's Conversaciones and had no
 * way to reach support from there. This opens THE SAME conversation the
 * website button opens for their account (the server keys it on the partner
 * either way), with the same agents seated, and shows it in Discuss.
 *
 * Hidden for the agents themselves: the server says who may ask through
 * `session_info`, and the route refuses the rest anyway.
 */
export class SupportRequestButton extends Component {
    static template = "website_pwa_chat.SupportRequestButton";
    static props = {};

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.dialog = useService("dialog");
        this.state = useState({busy: false});
    }

    get visible() {
        return Boolean(session.website_pwa_chat_can_request_support);
    }

    onClick() {
        if (this.state.busy) {
            return;
        }
        if (session.website_pwa_chat_support_asks_name) {
            this.dialog.add(SupportNameDialog, {
                onConfirm: (identity) => this.request(identity),
            });
            return;
        }
        return this.request({});
    }

    async request({name, email} = {}) {
        this.state.busy = true;
        try {
            const {channel_id} = await rpc("/website_pwa_chat/support/request", {
                name,
                email,
            });
            const thread = await this.store.Thread.getOrFetch({
                model: "discuss.channel",
                id: channel_id,
            });
            thread?.setAsDiscussThread();
        } finally {
            this.state.busy = false;
        }
    }
}

// Between the mailboxes (20) and the channel categories (30): above the
// conversations, where somebody looking for help looks first.
discussSidebarItemsRegistry.add("website_pwa_chat_support_request", SupportRequestButton, {
    sequence: 25,
});
