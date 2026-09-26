/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {SoundEffects} from "@mail/core/common/sound_effects_service";
import {Store} from "@mail/core/common/store_service";
import {patch} from "@web/core/utils/patch";
import {session} from "@web/session";
import {chime, pageInView} from "@mail_push_guest/js/chime";
import {shouldChimeForChannelMessage} from "./message_chime_rules";

/**
 * Foreground chime in the backend web client.
 *
 * Core already has the sound (`mail.sound_effects` "new-message") and the
 * user's switch for it (Discuss notification settings, "message sound").
 * What it skips: every message on a phone-sized screen (`ui.isSmall`, where
 * it leaves everything to the push) and every non-mention in a channel,
 * which in the community channels is the case that matters. This listener
 * rings for those through core's own `_playSound`, which keeps core's checks
 * (the switch, the main tab only, Android left to the push notification).
 *
 * The throttle is shared with core's own plays (patch below), so the two
 * paths -- and the push worker's "notification displayed" -- never ring
 * twice for one message.
 */
patch(SoundEffects.prototype, {
    play(soundEffectName, {loop = false} = {}) {
        if (soundEffectName === "new-message" && !loop && !chime.take()) {
            return;
        }
        return super.play(...arguments);
    },
});

function conversationInView(channel) {
    let focused = false;
    try {
        // Core's own test (store_service.js): the top document, since the
        // web client may run framed.
        focused = parent.document.hasFocus();
    } catch {
        focused = pageInView();
    }
    return focused && Boolean(channel.isDisplayed);
}

patch(Store.prototype, {
    onStarted() {
        super.onStarted(...arguments);
        const communityIds = new Set(session.community_channel_ids || []);
        this.env.bus.addEventListener(
            "discuss.channel/new_message",
            ({detail: {channel, message, silent}}) => {
                const member = channel.self_member_id;
                const ring = shouldChimeForChannelMessage({
                    silent,
                    selfAuthored: message.isSelfAuthored,
                    isNotification: message.message_type === "notification",
                    isMember: Boolean(member),
                    memberMuted: Boolean(member?.mute_until_dt),
                    busy: Boolean(this.self?.im_status?.includes("busy")),
                    inView: conversationInView(channel),
                    channelType: channel.channel_type,
                    memberSetting: member?.custom_notifications || false,
                    userSetting: this.settings.channel_notifications || false,
                    mentioned: Boolean(message.partner_ids?.includes(this.self)),
                    communityChannel: communityIds.has(channel.id),
                });
                if (ring) {
                    this.env.services["mail.out_of_focus"]._playSound();
                }
            }
        );
    },
});
