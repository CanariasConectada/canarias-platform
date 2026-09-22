/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {Component, markup} from "@odoo/owl";
import {fields} from "@mail/core/common/record";
import {Store} from "@mail/core/common/store_service";
import {Thread} from "@mail/core/common/thread";
import {Thread as ThreadModel} from "@mail/core/common/thread_model";
import {patch} from "@web/core/utils/patch";

/**
 * The author's own held messages, inline at the bottom of the thread.
 *
 * Server side, `discuss.channel._to_store_defaults` ships the CURRENT
 * persona's pending rows as `cc_pending_messages` (a plain list of dicts:
 * id, state, body, date, rejection_reason -- never anybody else's rows), and
 * the `author_status` bus notification keeps the list live. This file only
 * declares the field and renders it.
 */
patch(ThreadModel.prototype, {
    setup() {
        super.setup(...arguments);
        this.cc_pending_messages = fields.Attr([]);
    },
});

/**
 * The empty-recordset contract of a held post, honoured client side.
 *
 * `discuss.channel.message_post` returns an EMPTY recordset when the message
 * is held, so `/mail/message/post` answers `message_id: false`. Core's
 * `Thread.post` would then look the message up, get nothing, and crash on
 * `message.author` -- leaving the optimistic temporary message on screen as
 * if it had been published, which is the exact lie a hold must not tell.
 *
 * Intercepting `doMessagePost` is the narrowest seam: dropping the temporary
 * message and returning nothing makes `Thread.post` take its existing
 * "no data" early exit, and the "Pending review" placeholder takes over the
 * moment the author's `author_status` bus notification lands.
 */
patch(Store.prototype, {
    async doMessagePost(params, tmpMessage) {
        const data = await super.doMessagePost(...arguments);
        if (data && !data.message_id) {
            if (data.store_data) {
                this.insert(data.store_data);
            }
            tmpMessage?.delete();
            return undefined;
        }
        return data;
    },
});

export class CommunityPendingMessages extends Component {
    static template = "discuss_community_moderation.CommunityPendingMessages";
    static props = ["thread"];

    get entries() {
        return (this.props.thread.cc_pending_messages || []).map((entry) => ({
            ...entry,
            // Sanitised server side by the pending row's Html field; same
            // trust chain as a published message body.
            bodyMarkup: markup(entry.body || ""),
        }));
    }
}

Thread.components = {...Thread.components, CommunityPendingMessages};
