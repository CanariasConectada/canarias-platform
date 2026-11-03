/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";

/**
 * Single canonical string, mirrored from
 * `discuss_channel_moderation.models.discuss_channel_pending_message`
 * (BUS_AUTHOR_STATUS). The engine emits it towards the AUTHOR's own bus on
 * every state change of their held message; until this module, no Discuss
 * client listened (the engine's ROADMAP says as much).
 */
const AUTHOR_STATUS = "discuss.channel.moderation/author_status";

export const discussCommunityModerationService = {
    dependencies: ["bus_service", "mail.store"],
    start(env, services) {
        const store = services["mail.store"];
        services.bus_service.subscribe(AUTHOR_STATUS, (payload) => {
            const thread = store.Thread.get({
                model: "discuss.channel",
                id: payload.channel_id,
            });
            if (!thread) {
                // The author is not looking at (or has never fetched) the
                // channel: the store attr covers them on the next fetch.
                return;
            }
            const current = thread.cc_pending_messages || [];
            const previous = current.find((entry) => entry.id === payload.id);
            const entries = current.filter((entry) => entry.id !== payload.id);
            if (payload.state === "pending") {
                entries.push({
                    id: payload.id,
                    state: "pending",
                    body: payload.body || "",
                    date: payload.date || "",
                    rejection_reason: "",
                });
            } else if (payload.state === "rejected") {
                // Keep the body on screen next to the reason: "your message
                // was rejected" with no message would read as noise.
                entries.push({
                    id: payload.id,
                    state: "rejected",
                    body: payload.body || previous?.body || "",
                    date: payload.date || previous?.date || "",
                    rejection_reason: payload.rejection_reason || "",
                });
            }
            // "approved": the entry is simply dropped -- the published
            // message reaches the thread through the normal channel
            // notifications, so the badge disappears and the message
            // appears, in that order.
            entries.sort((a, b) => a.id - b.id);
            thread.cc_pending_messages = entries;
        });
    },
};

registry
    .category("services")
    .add("discuss_community_moderation", discussCommunityModerationService);
