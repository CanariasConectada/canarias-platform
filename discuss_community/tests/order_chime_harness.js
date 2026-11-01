/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Loads the THREE shipped scripts that decide backend sounds together --
 * mail_push_guest's chime.js, this module's message_chime.js (+ rules) and
 * website_sale_merchant_alert's order_push_chime.js -- over stubs of core's
 * Store, SoundEffects and out-of-focus service, and plays a timeline of chat
 * messages and order pushes against a fake clock.
 *
 * Usage:  node order_chime_harness.js <input.json>
 *   input: {paths: {chime, rules, message, order}, cases: [{name, steps}]}
 *   step:  {at: ms, chat: true} | {at: ms, order: true}
 * stdout: {"cases": {<name>: [{kind}, ...played]}}; assertions in Python.
 */
"use strict";

const fs = require("fs");

function factory(source, depNames, exported) {
    const body = source
        .split("\n")
        .filter((line) => !/^import\s/.test(line))
        .join("\n")
        .replace(/^export\s+/gm, "");
    // eslint-disable-next-line no-new-func
    return new Function(
        "deps",
        `const {${depNames.join(", ")}} = deps;\n${body}\nreturn {${exported.join(", ")}};`
    );
}

/** Odoo's `patch`, as far as `super.method()` goes. */
function patch(target, extension) {
    const previous = {};
    for (const key of Object.getOwnPropertyNames(extension)) {
        previous[key] = target[key];
    }
    Object.setPrototypeOf(extension, previous);
    for (const key of Object.getOwnPropertyNames(extension)) {
        target[key] = extension[key];
    }
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

async function runCase(paths, testCase) {
    const clock = {now: 0};
    class FakeDate extends Date {
        static now() {
            return clock.now;
        }
    }
    const played = [];
    class SoundEffects {
        play(name, options = {}) {
            played.push({name, kind: options.ccKind || "message", at: clock.now});
        }
    }
    class Store {
        onStarted() {}
        onPushNotificationDisplayed() {}
    }
    const storage = {
        data: {},
        getItem(key) {
            return key in this.data ? this.data[key] : null;
        },
        setItem(key, value) {
            this.data[key] = String(value);
        },
        removeItem(key) {
            delete this.data[key];
        },
    };

    const chimeApi = factory(fs.readFileSync(paths.chime, "utf8"), ["Date"], [
        "Chime",
        "pageInView",
    ])({Date: FakeDate});
    const chime = new chimeApi.Chime({clock: () => clock.now, storage, player: () => {}});
    const rules = factory(fs.readFileSync(paths.rules, "utf8"), [], [
        "shouldChimeForChannelMessage",
    ])({});
    factory(
        fs.readFileSync(paths.message, "utf8"),
        [
            "SoundEffects",
            "Store",
            "patch",
            "session",
            "chime",
            "pageInView",
            "shouldChimeForChannelMessage",
        ],
        []
    )({
        SoundEffects,
        Store,
        patch,
        session: {community_channel_ids: []},
        chime,
        pageInView: () => false,
        shouldChimeForChannelMessage: rules.shouldChimeForChannelMessage,
    });
    factory(
        fs.readFileSync(paths.order, "utf8"),
        ["Store", "browser", "isAndroid", "patch", "Date"],
        []
    )({Store, browser: {}, isAndroid: () => false, patch, Date: FakeDate});

    const soundEffects = new SoundEffects();
    const listeners = {};
    const store = new Store();
    store.settings = {messageSound: true, channel_notifications: "mentions"};
    store.self = {im_status: "online"};
    store.env = {
        bus: {
            addEventListener(type, handler) {
                (listeners[type] = listeners[type] || []).push(handler);
            },
        },
        services: {
            "mail.sound_effects": soundEffects,
            // Core's `_playSound`, minus the checks the harness does not vary.
            "mail.out_of_focus": {
                canPlayAudio: true,
                multiTab: {isOnMainTab: async () => true},
                async _playSound() {
                    soundEffects.play("new-message");
                },
            },
        },
    };
    store.onStarted();

    for (const step of testCase.steps) {
        clock.now = step.at;
        if (step.chat) {
            for (const handler of listeners["discuss.channel/new_message"] || []) {
                handler({
                    detail: {
                        channel: {
                            id: 1,
                            channel_type: "chat",
                            self_member_id: {},
                            isDisplayed: false,
                        },
                        message: {
                            isSelfAuthored: false,
                            message_type: "comment",
                            partner_ids: [],
                        },
                        silent: false,
                    },
                });
            }
        }
        if (step.order) {
            store.onPushNotificationDisplayed({model: "sale.order", res_id: 1});
        }
        await flush();
    }
    return played;
}

async function main() {
    const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
    const cases = {};
    for (const testCase of input.cases) {
        cases[testCase.name] = await runCase(input.paths, testCase);
    }
    process.stdout.write(JSON.stringify({cases}));
}

main().catch((error) => {
    process.stdout.write(JSON.stringify({harnessError: String(error && error.stack)}));
    process.exit(1);
});
