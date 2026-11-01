/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * The foreground "new message" chime, shared by the backend web client and
 * the website pages.
 *
 * Only for an OPEN app or tab. A web push that arrives with the app closed
 * cannot choose its sound (browsers ignore the Notification API's `sound`
 * option); the phone plays its own notification sound, and the server side of
 * this module makes sure no push arrives silently.
 *
 * Framework-free on purpose (no imports, every browser API injectable), so
 * `tests/test_chime_js.py` can run it in node.
 */

/** At most one chime every this many milliseconds, whatever triggers it. */
export const CHIME_MIN_INTERVAL_MS = 2000;

/**
 * Core's own "message sound" preference (mail/static/src/core/common/
 * settings_model.js, `MESSAGE_SOUND`): the Discuss notification settings
 * write the string "false" there to mute. Reusing the key means ONE switch:
 * muting in Discuss mutes the website chat of the same host, and back.
 */
export const MESSAGE_SOUND_KEY = "mail.user_setting.message_sound";

/**
 * Core's "new message" sound, a short two-tone ding shipped with `mail`
 * (mail/static/src/audio/new-message.{ogg,mp3}). Reused instead of shipping
 * a second sound: the backend already plays it, so the website sounds the
 * same, and no third-party audio enters the repository.
 */
export const CHIME_SOUND_PATH = "/mail/static/src/audio/new-message";

/**
 * When the last chime of this origin played. In storage, not in memory, so
 * the throttle holds across documents: two tabs, or the website page and the
 * support chat framed inside it, would otherwise each ring for the same
 * message.
 */
export const CHIME_LAST_KEY = "mail_push_guest.chime_last_at";

/** Default player: one reused <audio> element, ogg where it plays. */
export function createAudioPlayer(AudioCtor = globalThis.Audio, path = CHIME_SOUND_PATH) {
    let audio = null;
    return function play() {
        if (typeof AudioCtor === "undefined") {
            return;
        }
        try {
            if (!audio) {
                audio = new AudioCtor();
                const ogg = audio.canPlayType && audio.canPlayType("audio/ogg; codecs=vorbis");
                audio.src = path + (ogg ? ".ogg" : ".mp3");
            }
            audio.currentTime = 0;
            // Autoplay policies reject until the visitor has interacted with
            // the page once. Nothing to do about it; never an error.
            Promise.resolve(audio.play()).catch(() => {});
        } catch {
            // No audio on this platform.
        }
    };
}

function defaultStorage() {
    try {
        return globalThis.localStorage || null;
    } catch {
        // Access itself throws when storage is blocked.
        return null;
    }
}

/**
 * The rules, in one place:
 * - never for the listener's own message;
 * - never for the conversation the person is looking at right now;
 * - never when the person muted it (default: on);
 * - at most once every `CHIME_MIN_INTERVAL_MS`, so a burst is one ding and
 *   two triggers for the same message (bus + push) are one ding too.
 */
export class Chime {
    constructor({
        clock = () => Date.now(),
        storage = defaultStorage(),
        player = createAudioPlayer(),
        minInterval = CHIME_MIN_INTERVAL_MS,
    } = {}) {
        this.clock = clock;
        this.storage = storage;
        this.player = player;
        this.minInterval = minInterval;
        this.lastAt = null;
        this.mutedFallback = false;
    }

    get muted() {
        try {
            return this.storage.getItem(MESSAGE_SOUND_KEY) === "false";
        } catch {
            return this.mutedFallback;
        }
    }

    set muted(value) {
        this.mutedFallback = Boolean(value);
        try {
            if (value) {
                this.storage.setItem(MESSAGE_SOUND_KEY, "false");
            } else {
                this.storage.removeItem(MESSAGE_SOUND_KEY);
            }
        } catch {
            // Storage unavailable (private mode): the choice lasts this page.
        }
    }

    /**
     * Claim the throttle slot. True when a sound may play now.
     *
     * Separate from `ring` so core's own sound effect (backend) can go
     * through the same throttle as ours.
     */
    take() {
        const now = this.clock();
        // Absolute distance: a stored value far in the future (clock changed,
        // a skewed write) must not mute the chime until that moment comes.
        const recent = [this.lastAt, this._storedLastAt()].some(
            (at) => at !== null && Math.abs(now - at) < this.minInterval
        );
        if (recent) {
            return false;
        }
        this.lastAt = now;
        try {
            this.storage.setItem(CHIME_LAST_KEY, String(now));
        } catch {
            // In-memory throttle only.
        }
        return true;
    }

    _storedLastAt() {
        try {
            const value = parseInt(this.storage.getItem(CHIME_LAST_KEY), 10);
            return Number.isFinite(value) ? value : null;
        } catch {
            return null;
        }
    }

    /**
     * @param {Object} [facts]
     * @param {boolean} [facts.ownMessage] the listener wrote it
     * @param {boolean} [facts.inView] the conversation is visible and focused
     * @returns {boolean} whether the chime played
     */
    ring({ownMessage = false, inView = false} = {}) {
        if (ownMessage || inView || this.muted) {
            return false;
        }
        if (!this.take()) {
            return false;
        }
        this.player();
        return true;
    }
}

/** The one instance of a page: every trigger shares its throttle. */
export const chime = new Chime();

/**
 * Whether the page itself is on screen and has the focus.
 *
 * `hasFocus` is false inside a frame whose parent holds the focus, which is
 * exactly the floating support window of the website: a reply that arrives
 * while the visitor browses the shop is not "in view".
 */
export function pageInView(doc = globalThis.document) {
    try {
        return doc.visibilityState === "visible" && doc.hasFocus();
    } catch {
        return false;
    }
}
