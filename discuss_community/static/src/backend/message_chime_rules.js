/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Whether a new Discuss message deserves the foreground chime.
 * Framework-free (no imports) so tests/test_message_chime_js.py runs it in
 * node; the wiring is message_chime.js.
 */

/**
 * Mirrors who the SERVER pushes (core's channel recipients plus the
 * community rule of `discuss_channel_notify.py`), so the open app sounds for
 * exactly the messages the closed app would have buzzed for:
 *
 * - never for the listener's own message, a system notification, a silent
 *   post, a conversation the user is not a member of, a muted member, a
 *   "busy" user, or the conversation on screen and focused;
 * - chats and groups: always;
 * - channels: by the member's setting, else the user's ("mentions" when
 *   neither is set). "all" rings, "no_notif" never, "mentions" when the user
 *   is mentioned -- or, in a community channel, when the MEMBER has no
 *   setting of its own (the owner's decision of 2026-09-26: the noticeboard
 *   notifies everybody who did not opt out).
 *
 * Known gap: the web client cannot tell an unset user-level setting from an
 * explicit "mentions" (core's `Settings` folds the first into the second),
 * so in a community channel an explicit user-level "mentions" still rings.
 *
 * @param {Object} facts
 * @returns {boolean}
 */
export function shouldChimeForChannelMessage({
    silent = false,
    selfAuthored = false,
    isNotification = false,
    isMember = false,
    memberMuted = false,
    busy = false,
    inView = false,
    channelType = "channel",
    memberSetting = false,
    userSetting = false,
    mentioned = false,
    communityChannel = false,
} = {}) {
    if (silent || selfAuthored || isNotification || !isMember || memberMuted || busy || inView) {
        return false;
    }
    if (channelType !== "channel") {
        return true;
    }
    const effective = memberSetting || userSetting || "mentions";
    if (effective === "no_notif") {
        return false;
    }
    if (effective === "all" || mentioned) {
        return true;
    }
    return communityChannel && !memberSetting;
}
