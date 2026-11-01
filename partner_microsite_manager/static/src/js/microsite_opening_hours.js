/** @odoo-module **/
// Copyright 2026 Canarias Conectada
// License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import publicWidget from "@web/legacy/js/public/public_widget";

/**
 * Opening-hours pill of the microsite homepage.
 *
 * The server renders the whole week into `data-microsite-hours` and leaves
 * the summary line blank; this widget fills in "today" and the open/closed
 * badge from the visitor's clock. Doing it here rather than server-side is
 * deliberate: the rendered homepage can sit in a worker cache for a long
 * while, and a stale "open now" is worse than showing nothing.
 */
publicWidget.registry.MicrositeOpeningHours = publicWidget.Widget.extend({
    selector: "[data-microsite-hours]",

    start() {
        this._render();
        return this._super(...arguments);
    },

    /**
     * Minutes since midnight for the shop's timezone, plus the weekday index
     * in `date.weekday()` order (Monday = 0), both read in that timezone.
     *
     * `Intl` is asked for the parts rather than building a Date from a
     * locale string: the latter is what the legacy platform did and it
     * silently produced the browser's own day whenever the format was not
     * the one V8 expects.
     */
    _nowInTimezone(timezone) {
        let parts;
        try {
            parts = new Intl.DateTimeFormat("en-US", {
                timeZone: timezone,
                weekday: "short",
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
            }).formatToParts(new Date());
        } catch {
            // An unknown tz string must not take the whole pill down.
            return null;
        }
        const value = (type) => (parts.find((p) => p.type === type) || {}).value;
        const weekdays = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
        const day = weekdays[value("weekday")];
        // "24" is how some engines spell midnight under hour12: false.
        const hour = parseInt(value("hour"), 10) % 24;
        const minute = parseInt(value("minute"), 10);
        if (day === undefined || isNaN(hour) || isNaN(minute)) {
            return null;
        }
        return { day, minutes: hour * 60 + minute };
    },

    _toMinutes(value) {
        const [hours, minutes] = String(value).split(":");
        return parseInt(hours, 10) * 60 + parseInt(minutes, 10);
    },

    _isOpen(ranges, minutes) {
        return ranges.some(([start, end]) => {
            const from = this._toMinutes(start);
            const to = this._toMinutes(end);
            // A range that wraps past midnight (22:00-02:00) is two windows.
            return from <= to
                ? minutes >= from && minutes <= to
                : minutes >= from || minutes <= to;
        });
    },

    _render() {
        let data;
        try {
            data = JSON.parse(this.el.dataset.micrositeHours || "{}");
        } catch {
            return;
        }
        const days = data.days || [];
        const now = this._nowInTimezone(data.timezone);
        if (!now || !days.length) {
            return;
        }
        const today = days[now.day];
        if (!today) {
            return;
        }
        const ranges = today.ranges || [];
        const open = this._isOpen(ranges, now.minutes);

        const dayEl = this.el.querySelector("[data-hours-day]");
        const hoursEl = this.el.querySelector("[data-hours-today]");
        const statusEl = this.el.querySelector("[data-hours-status]");
        if (dayEl) {
            dayEl.textContent = today.label;
        }
        if (hoursEl) {
            hoursEl.textContent = ranges.length
                ? ranges.map(([from, to]) => `${from} - ${to}`).join(" / ")
                : data.closedLabel || "";
        }
        if (statusEl) {
            statusEl.textContent = open ? data.openLabel : data.closedLabel;
            statusEl.classList.add(open ? "text-success" : "text-danger");
        }
        // Highlight today's row inside the expanded body.
        const row = this.el.querySelector(`[data-hours-row="${now.day}"]`);
        if (row) {
            row.classList.add("fw-bold");
        }
    },
});

export default publicWidget.registry.MicrositeOpeningHours;
