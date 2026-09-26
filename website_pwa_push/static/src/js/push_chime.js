/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {chime, pageInView} from "@mail_push_guest/js/chime";
import {isAndroid} from "@web/core/browser/feature_detection";
import {user} from "@web/core/user";
import {session} from "@web/session";

/**
 * Whether the pushed message was written by the person on this page.
 *
 * The server never pushes a message to its author, so this is a guard, not
 * the rule. The worker passes on the author ids mail_push_guest puts in the
 * payload's `data`; the page knows its partner (`user.partnerId`) and, for
 * a guest, its own id from the session (`cc_guest_id`, website_pwa_push's
 * ir.http).
 */
export function isOwnPush(payload, {partnerId, guestId} = {}) {
    const authorPartner = Number(payload?.author_partner_id) || 0;
    const authorGuest = Number(payload?.author_guest_id) || 0;
    return Boolean(
        (authorPartner && authorPartner === partnerId) ||
            (authorGuest && authorGuest === guestId)
    );
}

/**
 * Foreground chime for a push the website worker has just shown.
 *
 * The worker posts `notification-displayed` to every open page of the origin
 * (the same message core's backend worker posts). A closed app runs no page
 * script: there the phone's own notification sound is all there is, and all
 * a web push can have.
 *
 * Android with the permission granted is left to the notification itself,
 * which already sounds and follows the phone's silent mode -- the same rule
 * core applies in its web client (`OutOfFocusService._playSound`).
 */
export function onWorkerMessage(
    event,
    {
        doc = document,
        android = isAndroid(),
        persona = {partnerId: user.partnerId, guestId: session.cc_guest_id},
    } = {}
) {
    const {type, payload} = event.data || {};
    if (type !== "notification-displayed") {
        return false;
    }
    if (android && globalThis.Notification?.permission === "granted") {
        return false;
    }
    const channelId = Number(payload?.res_id);
    const showsThisConversation =
        payload?.model === "discuss.channel" &&
        Number.isInteger(channelId) &&
        Boolean(doc.querySelector(`.o_cc_chat[data-channel-id="${channelId}"]`));
    // The floating support window is an iframe: while the visitor types in
    // it, the conversation lives in the frame, not in this document.
    const typingInAFrame = doc.activeElement?.tagName === "IFRAME";
    return chime.ring({
        ownMessage: isOwnPush(payload, persona),
        inView: pageInView(doc) && (showsThisConversation || typingInAFrame),
    });
}

globalThis.navigator?.serviceWorker?.addEventListener("message", (event) => onWorkerMessage(event));
