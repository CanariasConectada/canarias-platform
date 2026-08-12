/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Tiny progressive enhancement: reflect "this product is in the compare list"
 * on its card button, so the modern active state (filled plum) shows without
 * touching core's comparison interaction. Core toggles the list in
 * localStorage under "comparelist_product_ids"; we read it and mark the
 * matching buttons pressed. Purely visual — the interaction still owns the
 * behaviour. */
(function () {
    "use strict";

    var KEY = "comparelist_product_ids";

    function comparedIds() {
        try {
            return JSON.parse(localStorage.getItem(KEY) || "[]") || [];
        } catch (e) {
            return [];
        }
    }

    function paint() {
        var ids = comparedIds();
        document.querySelectorAll(".o_wscc_compare_btn").forEach(function (btn) {
            var pid = parseInt(btn.dataset.productProductId, 10);
            var on = ids.indexOf(pid) !== -1;
            btn.classList.toggle("active", on);
            btn.setAttribute("aria-pressed", on ? "true" : "false");
        });
    }

    function start() {
        paint();
        // Core re-writes the list on click; repaint shortly after any click on
        // a compare button, and whenever another tab changes the list.
        document.addEventListener("click", function (ev) {
            if (ev.target.closest(".o_wscc_compare_btn")) {
                setTimeout(paint, 100);
            }
        });
        window.addEventListener("storage", function (ev) {
            if (ev.key === KEY) {
                paint();
            }
        });
    }

    if (document.readyState !== "loading") {
        start();
    } else {
        document.addEventListener("DOMContentLoaded", start);
    }
})();
