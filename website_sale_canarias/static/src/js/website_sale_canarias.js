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
        // Keep the toggle honest when the cascade repopulates the select or
        // sets its value from code: any change event re-reads the label.
        select.addEventListener("change", function () {
            toggle.textContent = label();
        });
        select.addEventListener("wsc:refresh", function () {
            toggle.textContent = label();
        });
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
        // The active category, kept here because the two filter instances
        // (sidebar and offcanvas) can disagree after an AJAX change.
        category: null,

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

        // Preserve the OTHER active filters, mirroring the server-rendered
        // chip's keep(shop_path, category=0): the category is gone, search
        // and price survive.
        buildClearHref: function (result) {
            var params = new URLSearchParams();
            if (result.search) {
                params.set("search", result.search);
            }
            if (result.price && result.price.min) {
                params.set("min_price", result.price.min);
            }
            if (result.price && result.price.max) {
                params.set("max_price", result.price.max);
            }
            var qs = params.toString();
            return "/shop" + (qs ? "?" + qs : "");
        },

        // Where a freshly created chip belongs: the same spot the QWeb view
        // puts it — right before the tile row when there is one, otherwise
        // right before the grid's own wrapper (or the grid itself, on the
        // rare page that has no wrapper at all, e.g. zero products).
        findChipAnchor: function () {
            return (
                document.querySelector(".o_wsc_category_tiles_row") ||
                document.querySelector(".o_wsale_products_grid_table_wrapper") ||
                this.grid()
            );
        },

        // Builds the exact markup the server renders for the chip (same
        // wrapper/classes/ids as templates.xml's shop_category_tiles view)
        // and inserts it at findChipAnchor(). Returns the new #wsc_category
        // _chip element, or null when there is nowhere sane to put it.
        createCategoryChip: function () {
            var anchor = this.findChipAnchor();
            if (!anchor) {
                return null;
            }
            var wrapper = document.createElement("div");
            wrapper.className =
                "wd-active-filters mb-3 d-flex flex-wrap gap-2 align-items-center";
            wrapper.innerHTML =
                '<span id="wsc_category_chip" class="badge bg-primary wd-filter-chip d-inline-flex align-items-center">' +
                '<i class="fa fa-folder me-1"></i>' +
                '<span class="o_wsc_category_chip_label"></span>' +
                '<a class="wd-filter-link wd-filter-chip-x" aria-label="Quitar filtro de categoría">×</a>' +
                "</span>";
            anchor.insertAdjacentElement("beforebegin", wrapper);
            return wrapper.querySelector("#wsc_category_chip");
        },

        // The tile row and its "×" clear the filter with a full navigation
        // (see the QWeb view), so THEY never go stale. The chip is the one
        // piece of chrome the grid-swapping AJAX loader would otherwise
        // leave behind: it is only server-rendered for whatever category
        // the page loaded on, so an unfiltered /shop that gets a category
        // picked afterwards in the sidebar select starts with no chip at
        // all. Called on every AJAX response so the chip always names the
        // CURRENT filter — created when missing, updated in place, or
        // removed (wrapper included) when there is none.
        syncCategoryChip: function (result) {
            var chip = document.getElementById("wsc_category_chip");
            if (!result.category_id) {
                if (chip) {
                    var oldWrapper = chip.closest(".wd-active-filters");
                    (oldWrapper || chip).remove();
                }
                return;
            }
            if (!chip) {
                chip = this.createCategoryChip();
                if (!chip) {
                    return;
                }
            }
            var label = chip.querySelector(".o_wsc_category_chip_label");
            if (label) {
                label.textContent = result.category_name || "";
            }
            var clearLink = chip.querySelector(".wd-filter-chip-x");
            if (clearLink) {
                clearLink.setAttribute("href", this.buildClearHref(result));
            }
        },

        updateChrome: function (result) {
            this.syncCategoryChip(result);
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

    function categoryTree(suffix) {
        var node =
            document.getElementById("wsc_category_data" + (suffix || "")) ||
            document.getElementById("wsc_category_data");
        if (!node) {
            return [];
        }
        try {
            return JSON.parse(node.dataset.tree || "[]");
        } catch (error) {
            return [];
        }
    }

    function findNode(nodes, id) {
        for (var i = 0; i < nodes.length; i++) {
            if (String(nodes[i].id) === String(id)) {
                return nodes[i];
            }
        }
        return null;
    }

    /*
     * The filter cards render twice — the desktop sidebar and the mobile
     * offcanvas — each with its own id suffix, so every control is wired
     * per instance. The loader tracks the active category itself: the two
     * instances are never visible at the same breakpoint, so the one the
     * visitor last touched is the truth.
     */
    function wireFilterGroup(suffix) {
        // Zone switcher: each option's value is another marketplace's /shop
        // URL, so picking a zone is a plain navigation — no AJAX, the other
        // site renders its own shop.
        var zoneSelect = document.getElementById("wsc_zone_select" + suffix);
        if (zoneSelect) {
            enhanceSelect(zoneSelect);
            zoneSelect.addEventListener("change", function () {
                if (zoneSelect.value) {
                    window.location.href = zoneSelect.value;
                }
            });
        }

        var select = document.getElementById("wsc_category_select" + suffix);
        var subSelect = document.getElementById("wsc_subcategory_select" + suffix);
        var subWrap = document.getElementById("wsc_subcategory_wrap" + suffix);
        var tree = categoryTree(suffix);
        if (select) {
            enhanceSelect(select);
            select.addEventListener("change", function () {
                // Repopulate the subcategory level for the new main
                // category; the products load on the main category itself
                // (the endpoint includes its children).
                if (subSelect && subWrap) {
                    while (subSelect.options.length > 1) {
                        subSelect.remove(1);
                    }
                    subSelect.value = "";
                    var node = select.value ? findNode(tree, select.value) : null;
                    var children = (node && node.children) || [];
                    children.forEach(function (child) {
                        var option = document.createElement("option");
                        option.value = child.id;
                        option.textContent = child.name;
                        subSelect.appendChild(option);
                    });
                    subWrap.classList.toggle("d-none", !children.length);
                    subSelect.dispatchEvent(new Event("wsc:refresh"));
                }
                loader.category = select.value || null;
                loader.load(loader.category, currentSearch());
            });
        }
        if (subSelect) {
            enhanceSelect(subSelect);
            subSelect.addEventListener("change", function () {
                loader.category =
                    subSelect.value || (select && select.value) || null;
                loader.load(loader.category, currentSearch());
            });
        }
    }

    function wirePriceInputs() {
        var inputs = document.querySelectorAll(
            'input[name="min_price"], input#min_price, ' +
                'input[name="max_price"], input#max_price'
        );
        inputs.forEach(function (input) {
            if (input.dataset.wscWired) {
                return;
            }
            input.dataset.wscWired = "1";
            input.addEventListener("change", function () {
                // Read min and max from the input's OWN filter block: the
                // price widget renders once per filter instance and the
                // untouched instance may hold stale values.
                var scope =
                    input.closest("#o_wsale_price_range_option") || document;
                loader.minPrice =
                    parseFloat(
                        (scope.querySelector('input[name="min_price"]') || {})
                            .value
                    ) || 0;
                loader.maxPrice =
                    parseFloat(
                        (scope.querySelector('input[name="max_price"]') || {})
                            .value
                    ) || 0;
                loader.load(loader.category, currentSearch());
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
    }

    function setup() {
        loader.category =
            new URLSearchParams(window.location.search).get("category") || null;

        ["", "_offcanvas"].forEach(wireFilterGroup);
        wirePriceInputs();

        rewriteMerchantLinks();

        // Back/forward must not leave a grid that disagrees with the URL.
        // The AJAX loader rewrites the URL with pushState but the browser
        // restores the DOM from its own cache on history navigation, so the
        // safe, simple answer is a full reload to whatever the URL now says.
        window.addEventListener("popstate", function () {
            window.location.reload();
        });
    }

    if (document.readyState !== "loading") {
        setup();
    } else {
        document.addEventListener("DOMContentLoaded", setup);
    }
})();
