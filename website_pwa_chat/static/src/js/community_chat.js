/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";
import {Interaction} from "@web/public/interaction";
import {rpc} from "@web/core/network/rpc";
import {_t} from "@web/core/l10n/translation";

// The two bus notifications this page listens to.
//
// `discuss.channel/new_message` is core's, broadcast to every subscriber of
// the channel (mail/models/discuss/discuss_channel.py:944). Its payload is a
// `Store` graph meant for the backend Discuss client, so it is used ONLY as a
// doorbell: something happened, go and ask.
const NEW_MESSAGE = "discuss.channel/new_message";
// `discuss.channel.moderation/author_status` is ours, and it is addressed to
// ONE persona -- the author of a held message -- because it is sent to their
// own bus channel (discuss_channel_moderation, `_notify_author`). Nobody else
// receives it, so nothing here has to filter for privacy.
const AUTHOR_STATUS = "discuss.channel.moderation/author_status";

/**
 * The community chat page.
 *
 * WHY THIS IS HAND-WRITTEN AND NOT ODOO'S DISCUSS CLIENT. The Discuss OWL
 * components live in `web.assets_backend`. The only shipped way to get them
 * onto the public site is installing `im_livechat`, whose manifest injects
 * `im_livechat.assets_embed_core` into `web.assets_frontend` -- for all 218
 * websites of this database, whether they have a chat page or not. That is a
 * platform-wide asset decision taken to save a few hundred lines here, and it
 * would also couple this page to an embed API written for a support widget.
 *
 * What is used instead is the one messaging piece core ALREADY puts in the
 * frontend bundle: `bus` (bus/__manifest__.py:20-27). Everything else is this
 * file: append a message, show a held one, post through the public route.
 */
export class CommunityChat extends Interaction {
    static selector = ".o_cc_chat";

    setup() {
        this.channelId = parseInt(this.el.dataset.channelId, 10);
        this.messagesEl = this.el.querySelector(".o_cc_chat_messages");
        this.pendingZoneEl = this.el.querySelector(".o_cc_chat_pending_zone");
        this.inputEl = this.el.querySelector(".o_cc_chat_input");
        this.errorEl = this.el.querySelector(".o_cc_chat_error");
        this.lastMessageId = this.readLastMessageId();
        this.isSending = false;
    }

    start() {
        if (!this.channelId) {
            return;
        }
        this.listen();
        this.addListener(this.el, "submit", (event) => {
            event.preventDefault();
            this.send();
        });
        // Enter sends, Shift+Enter breaks the line. On a phone the send
        // button is right there, so this is for the people on a keyboard.
        this.addListener(this.inputEl, "keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                this.send();
            }
        });
        // The floating window's idle-close (support_window.js) needs to know
        // the visitor typed something, and this page is what the window
        // frames -- often cross-subdomain, where the parent cannot read a
        // single keystroke of a document it does not own. `postMessage`
        // is the one channel that crosses that boundary by design, so it
        // is the only reliable way to say "someone is here" regardless of
        // which of the platform's 218 hosts is doing the framing.
        this.addListener(this.inputEl, "input", () => this.notifyParentActivity());
        this.scrollToBottom();
    }

    notifyParentActivity() {
        if (window.parent && window.parent !== window) {
            window.parent.postMessage({type: "o_cc_chat_activity"}, "*");
        }
    }

    /**
     * Subscribe to the channel and to this persona's own notifications.
     *
     * Only the CHANNEL has to be asked for by name. The persona's own bus
     * channel is added server side from the session: the guest cookie for a
     * visitor (mail/models/discuss/ir_websocket.py:27-29) and the partner for
     * a logged-in user (bus/models/ir_websocket.py:26-27). That is also why
     * the page creates the guest before rendering -- the cookie has to exist
     * before this subscription goes out.
     *
     * Asking for `discuss.channel_<id>` is not a way in either: the server
     * resolves the string through a `search()` that the record rule filters,
     * so a forged id in the DOM subscribes to nothing.
     */
    listen() {
        const bus = this.services.bus_service;
        this.onNewMessage = (payload) => {
            if (payload.id === this.channelId) {
                this.refreshMessages();
            }
        };
        this.onAuthorStatus = (payload) => {
            if (payload.channel_id !== this.channelId) {
                return;
            }
            if (payload.state === "rejected") {
                this.showRejection(payload.rejection_reason);
            }
            // Held, approved and rejected all change what the visitor has
            // waiting, so all three re-read it. An approved message arrives
            // separately, through NEW_MESSAGE.
            this.refreshPending();
        };
        bus.subscribe(NEW_MESSAGE, this.onNewMessage);
        bus.subscribe(AUTHOR_STATUS, this.onAuthorStatus);
        this.registerCleanup(() => {
            bus.unsubscribe(NEW_MESSAGE, this.onNewMessage);
            bus.unsubscribe(AUTHOR_STATUS, this.onAuthorStatus);
            bus.deleteChannel(`discuss.channel_${this.channelId}`);
        });
        bus.addChannel(`discuss.channel_${this.channelId}`);
    }

    // ------------------------------------------------------------------
    // Posting
    // ------------------------------------------------------------------

    /**
     * Post through core's own public route.
     *
     * `/mail/message/post` is where `discuss_channel_moderation` hooks in, so
     * this is not a detour: posting anywhere else would skip the moderation
     * gate. A held message comes back as `message_id: False` -- the module
     * returns an empty recordset and the controller reads `.id` off it -- and
     * that falsy id is the ONLY signal that the message was held rather than
     * published.
     */
    async send() {
        const body = (this.inputEl.value || "").trim();
        if (!body || this.isSending) {
            return;
        }
        this.isSending = true;
        this.notifyParentActivity();
        this.hideError();
        let result = null;
        try {
            result = await this.waitFor(
                rpc("/mail/message/post", {
                    thread_model: "discuss.channel",
                    thread_id: this.channelId,
                    post_data: {
                        body: body,
                        message_type: "comment",
                        subtype_xmlid: "mail.mt_comment",
                    },
                })
            );
        } catch (error) {
            this.isSending = false;
            // The quota ceilings of the moderation module come back here as
            // plain UserErrors with a sentence the author is meant to read.
            this.showError(error.data?.message || error.message);
            return;
        }
        this.isSending = false;
        this.protectSyncAfterAsync(() => {
            this.inputEl.value = "";
        })();
        if (result && result.message_id) {
            // Published straight away: NEW_MESSAGE will bring it, but the
            // author should not have to wait for a round trip on the bus.
            this.refreshMessages();
        } else {
            this.refreshPending();
        }
    }

    // ------------------------------------------------------------------
    // Reading
    // ------------------------------------------------------------------

    async refreshMessages() {
        const result = await this.waitFor(
            rpc("/website_pwa_chat/messages", {
                channel_id: this.channelId,
                after: this.lastMessageId || null,
            })
        );
        this.protectSyncAfterAsync(() => {
            for (const message of result.messages) {
                this.appendMessage(message);
            }
            if (result.messages.length) {
                this.scrollToBottom();
            }
        })();
    }

    async refreshPending() {
        const result = await this.waitFor(
            rpc("/website_pwa_chat/pending", {channel_id: this.channelId})
        );
        this.protectSyncAfterAsync(() => {
            // Server-rendered from the same QWeb template the page was built
            // with, so the wording of the invitation to register exists once.
            this.pendingZoneEl.innerHTML = result.html;
        })();
    }

    // ------------------------------------------------------------------
    // DOM
    // ------------------------------------------------------------------

    readLastMessageId() {
        const nodes = this.el.querySelectorAll("[data-message-id]");
        const last = nodes[nodes.length - 1];
        return last ? parseInt(last.dataset.messageId, 10) : 0;
    }

    appendMessage(message) {
        if (this.el.querySelector(`[data-message-id="${message.id}"]`)) {
            // The doorbell can ring twice for the same message (two tabs, a
            // reconnect replaying notifications). Ids make that harmless.
            return;
        }
        const emptyEl = this.messagesEl.querySelector(".o_cc_chat_empty");
        if (emptyEl) {
            emptyEl.remove();
        }
        const messageEl = document.createElement("div");
        messageEl.className = `o_cc_chat_message${message.mine ? " o_cc_chat_mine" : ""}`;
        messageEl.dataset.messageId = message.id;

        const metaEl = document.createElement("div");
        metaEl.className = "o_cc_chat_meta small text-muted";
        const authorEl = document.createElement("span");
        authorEl.className = "fw-bold o_cc_chat_author";
        // textContent, not innerHTML: a guest picks their own display name.
        authorEl.textContent = message.author;
        const dateEl = document.createElement("span");
        dateEl.className = "o_cc_chat_date";
        dateEl.textContent = message.date;
        metaEl.append(authorEl, dateEl);

        const bodyEl = document.createElement("div");
        bodyEl.className = "o_cc_chat_body";
        // innerHTML here and nowhere else: `mail.message.body` is an Html
        // field, sanitised by the ORM on write, and this is the same markup
        // the server put in the page with `t-out`. Escaping it would show
        // visitors the tags of their own line breaks.
        bodyEl.innerHTML = message.body;

        messageEl.append(metaEl, bodyEl);
        this.messagesEl.append(messageEl);
        this.lastMessageId = Math.max(this.lastMessageId, message.id);
    }

    showRejection(reason) {
        const noticeEl = document.createElement("div");
        noticeEl.className = "alert alert-secondary mt-3 o_cc_chat_rejected";
        noticeEl.setAttribute("role", "status");
        noticeEl.textContent = reason
            ? _t(
                  "Esta vez no hemos podido publicar tu mensaje: %s. Puedes escribir otro cuando quieras.",
                  reason
              )
            : _t(
                  "Esta vez no hemos podido publicar tu mensaje. Puedes escribir otro cuando quieras."
              );
        this.pendingZoneEl.after(noticeEl);
    }

    showError(message) {
        this.protectSyncAfterAsync(() => {
            this.errorEl.textContent =
                message || _t("No hemos podido enviar tu mensaje. Inténtalo otra vez.");
            this.errorEl.classList.remove("d-none");
        })();
    }

    hideError() {
        this.errorEl.textContent = "";
        this.errorEl.classList.add("d-none");
    }

    scrollToBottom() {
        this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }
}

registry.category("public.interactions").add("website_pwa_chat.chat", CommunityChat);
