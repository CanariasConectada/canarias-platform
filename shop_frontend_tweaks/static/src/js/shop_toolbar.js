/* Shop toolbar behaviour.
 * Formerly an inline <script> on website_sale.products' root, rendered
 * after </html> and re-parsed on every page load. setViewMode stays a
 * window global: the toolbar buttons (here and in zones_toolbar_fix)
 * call it from onclick attributes.
 */
(function () {
    "use strict";

    // Persist view mode (grid/list) in localStorage
    function setViewMode(mode) {
        var grid = document.getElementById("o_wsale_products_grid");
        if (grid) {
            if (mode === "list") {
                grid.classList.add("view-mode-list");
                grid.classList.remove("view-mode-grid");
            } else {
                grid.classList.add("view-mode-grid");
                grid.classList.remove("view-mode-list");
            }
            document
                .querySelectorAll(".view-mode-toggle button")
                .forEach(function (btn) {
                    btn.classList.remove("active");
                    if (btn.dataset.view === mode) {
                        btn.classList.add("active");
                    }
                });
            localStorage.setItem("microsite_view_mode", mode);
        }
    }
    window.setViewMode = setViewMode;

    function restore() {
        var savedMode = localStorage.getItem("microsite_view_mode");
        if (savedMode) {
            setViewMode(savedMode);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", restore);
    } else {
        restore();
    }
})();
