/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

/*
 * The aggregated shop's client side, three small parts:
 *
 * 1. The category <select> is upgraded to the same searchable dropdown the
 *    directory uses (its .wd-select CSS ships with website_directory, a
 *    declared dependency) so both pages speak one visual language.
 * 2. Category and price changes fetch /shop/ajax/products and swap the grid
 *    in place — no page reload. Any error falls back to a full navigation,
 *    which is the behaviour the page would have had anyway.
 * 3. On an aggregated shop every server-rendered card carries the owner's
 *    microsite domain (data-wsc-merchant-domain); product links inside it
 *    are rewritten to open the merchant's own shop in a new tab.
 */
(function () {
    "use strict";

    var SEARCH_FROM = 8;

    /* ---------------------------------------------------------------- */
    /* 1. Searchable dropdown (the directory's wd-select look)           */
    /* ---------------------------------------------------------------- */
    function enhanceSelect(select) {
        if (!select || select.dataset.wscEnhanced) {
            return;
        }
        select.dataset.wscEnhanced = "1";
        select.classList.add("wd-select-native");

        var wrap = document.createElement("div");
        wrap.className = "wd-select";
        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(select);

        var toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "form-select text-start wd-select-toggle";
        wrap.appendChild(toggle);

        var panel = document.createElement("div");
        panel.className = "wd-select-panel d-none";
        wrap.appendChild(panel);

        var search = null;
        var list = document.createElement("div");
        list.className = "wd-select-options";

        function label() {
            var option = select.options[select.selectedIndex];
            return option ? option.textContent : "";
        }

        function close() {
            panel.classList.add("d-none");
        }

        function renderOptions(filter) {
            list.innerHTML = "";
            var needle = (filter || "").toLowerCase();
            var shown = 0;
            Array.prototype.forEach.call(select.options, function (option) {
                var text = option.textContent;
                if (needle && text.toLowerCase().indexOf(needle) === -1) {
                    return;
                }
                shown += 1;
                var row = document.createElement("div");
                row.className =
                    "wd-select-option" + (option.selected ? " active" : "");
                row.textContent = text;
                row.addEventListener("click", function () {
                    select.value = option.value;
                    toggle.textContent = text;
                    close();
                    select.dispatchEvent(new Event("change", {bubbles: true}));
                });
                list.appendChild(row);
            });
            if (!shown) {
                var empty = document.createElement("div");
                empty.className = "wd-select-empty";
                empty.textContent = "Sin resultados";
                list.appendChild(empty);
            }
        }

        function open() {
            panel.innerHTML = "";
            if (select.options.length >= SEARCH_FROM) {
                search = document.createElement("input");
                search.type = "text";
                search.placeholder = "Buscar...";
                search.className = "form-control form-control-sm wd-select-search";
                search.addEventListener("input", function () {
                    renderOptions(search.value);
                });
                panel.appendChild(search);
            }
            panel.appendChild(list);
            renderOptions("");
            panel.classList.remove("d-none");
            if (search) {
                search.focus();
            }
        }

        toggle.textContent = label();
        toggle.addEventListener("click", function (event) {
            event.preventDefault();
            if (panel.classList.contains("d-none")) {
                open();
            } else {
                close();
            }
        });
        document.addEventListener("click", function (event) {
            if (!wrap.contains(event.target)) {
                close();
            }
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                close();
            }
        });
    }

    /* ---------------------------------------------------------------- */
    /* 3. Product links point at the merchant's own shop                 */
    /* ---------------------------------------------------------------- */
    function rewriteMerchantLinks() {
        document
            .querySelectorAll("[data-wsc-merchant-domain]")
            .forEach(function (card) {
                var domain = card.getAttribute("data-wsc-merchant-domain");
                if (!domain) {
                    return;
                }
                card.querySelectorAll('a[href*="/shop/"]').forEach(function (link) {
                    var href = link.getAttribute("href");
                    if (!href || href.indexOf(domain) !== -1) {
                        return;
                    }
                    var match = href.match(/\/shop\/([^?#]+)/);
                    if (match) {
                        link.href = domain.replace(/\/$/, "") + "/shop/" + match[1];
                        link.target = "_blank";
                        link.rel = "noopener";
                    }
                });
            });
    }

    /* ---------------------------------------------------------------- */
    /* 2. AJAX filtering                                                 */
    /* ---------------------------------------------------------------- */
    var loader = {
        busy: false,
        minPrice: 0,
        maxPrice: 0,

        grid: function () {
            return (
                document.getElementById("o_wsale_products_grid") ||
                document.querySelector("#products_grid .o_wsale_products_grid_table") ||
                document.getElementById("products_grid")
            );
        },

        fallbackUrl: function (categoryId) {
            var url = categoryId ? "/shop?category=" + categoryId : "/shop";
            if (this.minPrice) {
                url += (url.indexOf("?") !== -1 ? "&" : "?") + "min_price=" + this.minPrice;
            }
            if (this.maxPrice) {
                url += (url.indexOf("?") !== -1 ? "&" : "?") + "max_price=" + this.maxPrice;
            }
            return url;
        },

        load: function (categoryId, search) {
            if (this.busy) {
                return;
            }
            var grid = this.grid();
            if (!grid) {
                window.location.href = this.fallbackUrl(categoryId);
                return;
            }
            this.busy = true;
            var self = this;
            var original = grid.innerHTML;
            grid.innerHTML =
                '<div class="text-center py-5 col-12">' +
                '<i class="fa fa-spinner fa-spin fa-2x text-primary"></i>' +
                '<p class="mt-3 text-muted">Cargando productos...</p></div>';

            var params = new URLSearchParams();
            if (categoryId) {
                params.append("category", categoryId);
            }
            if (search) {
                params.append("search", search);
            }
            if (this.minPrice) {
                params.append("min_price", this.minPrice);
            }
            if (this.maxPrice) {
                params.append("max_price", this.maxPrice);
            }
            var query = params.toString();

            fetch("/shop/ajax/products" + (query ? "?" + query : ""), {
                headers: {Accept: "application/json"},
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("HTTP " + response.status);
                    }
                    return response.json();
                })
                .then(function (result) {
                    if (result.error || result.html === undefined) {
                        throw new Error(result.error || "empty response");
                    }
                    grid.innerHTML = result.html;
                    self.updateChrome(result);
                    rewriteMerchantLinks();
                    var url = "/shop" + (query ? "?" + query : "");
                    window.history.pushState({}, "", url);
                })
                .catch(function () {
                    grid.innerHTML = original;
                    window.location.href = self.fallbackUrl(categoryId);
                })
                .finally(function () {
                    self.busy = false;
                });
        },

        updateChrome: function (result) {
            var banner = document.getElementById("wsc-active-filters");
            if (banner) {
                banner.remove();
            }
            var pagination = document.querySelector(
                ".o_wsale_products_grid_bottom, .pagination, .o_pager"
            );
            if (pagination) {
                pagination.style.display = result.filters_active ? "none" : "";
            }
            if (!result.filters_active) {
                return;
            }
            var grid = this.grid();
            if (!grid) {
                return;
            }
            var details = [];
            if (result.category_name) {
                details.push("categoría: " + result.category_name);
            }
            if (result.search) {
                details.push('búsqueda: "' + result.search + '"');
            }
            if (result.price && (result.price.min || result.price.max)) {
                details.push(
                    "precio: " + result.price.min + "€ - " + result.price.max + "€"
                );
            }
            var wrapper = document.createElement("div");
            wrapper.id = "wsc-active-filters";
            wrapper.className =
                "alert alert-info d-flex align-items-center justify-content-between mb-3";
            var info = document.createElement("div");
            var strong = document.createElement("strong");
            strong.textContent = "Mostrando " + result.count + " productos";
            info.appendChild(strong);
            if (details.length) {
                var small = document.createElement("small");
                small.className = "text-muted ms-2";
                small.textContent = "(" + details.join(", ") + ")";
                info.appendChild(small);
            }
            var clear = document.createElement("button");
            clear.type = "button";
            clear.className = "btn btn-sm btn-outline-primary";
            clear.textContent = "Limpiar filtros";
            clear.addEventListener("click", function () {
                window.location.href = "/shop";
            });
            wrapper.appendChild(info);
            wrapper.appendChild(clear);
            grid.insertAdjacentElement("beforebegin", wrapper);
        },
    };

    function currentSearch() {
        var input = document.querySelector('input[name="search"]');
        return input ? input.value : "";
    }

    function setup() {
        var select = document.getElementById("wsc_category_select");
        if (select) {
            enhanceSelect(select);
            select.addEventListener("change", function () {
                loader.load(select.value || null, currentSearch());
            });
        }

        ["min_price", "max_price"].forEach(function (name) {
            var input = document.querySelector(
                'input[name="' + name + '"], input#' + name
            );
            if (!input) {
                return;
            }
            input.addEventListener("change", function () {
                loader.minPrice =
                    parseFloat(
                        (document.querySelector('input[name="min_price"]') || {}).value
                    ) || 0;
                loader.maxPrice =
                    parseFloat(
                        (document.querySelector('input[name="max_price"]') || {}).value
                    ) || 0;
                var params = new URLSearchParams(window.location.search);
                loader.load(
                    (select && select.value) || params.get("category"),
                    currentSearch()
                );
            });
            // The stock price filter submits a GET form; with the AJAX
            // loader in charge that reload is pure flicker.
            var form = input.closest("form");
            if (form && !form.dataset.wscNoSubmit) {
                form.dataset.wscNoSubmit = "1";
                form.addEventListener("submit", function (event) {
                    event.preventDefault();
                });
            }
        });

        rewriteMerchantLinks();
    }

    if (document.readyState !== "loading") {
        setup();
    } else {
        document.addEventListener("DOMContentLoaded", setup);
    }
})();
