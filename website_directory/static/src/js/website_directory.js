/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Public directory frontend: cascading category filter, async search,
 * grid/list toggle, page size and AJAX pagination. Plain IIFE on purpose:
 * this only runs on the public page and needs no Odoo framework import.
 */
(function () {
    "use strict";

    var state = {
        categories: [],
        selected: [null, null, null],
        view: "grid",
        ppg: 21,
        page: 1,
        category: null,
        search: "",
        loading: false,
    };

    var MIN_SEARCH_LENGTH = 3;
    var SEARCH_DELAY_MS = 400;

    function byId(id) {
        return document.getElementById(id);
    }

    function init() {
        var dataNode = byId("wd_data");
        if (!dataNode) {
            return; // Not on the directory page.
        }
        var data = {};
        try {
            data = JSON.parse(dataNode.dataset.directory || "{}");
        } catch (error) {
            data = {};
        }
        state.categories = data.categories || [];
        state.selected = data.selected || [null, null, null];
        state.view = dataNode.dataset.view || "grid";
        state.ppg = parseInt(dataNode.dataset.ppg, 10) || 21;
        state.search = dataNode.dataset.search || "";
        state.category =
            state.selected[2] || state.selected[1] || state.selected[0] || null;

        initZoneSelect();
        initCategoryCascade();
        initAsyncSearch();
        initToolbar();
        initPagination();
        ["wd_zone_select", "wd_cat_l1", "wd_cat_l2", "wd_cat_l3"].forEach(
            function (id) {
                enhanceSelect(byId(id));
            }
        );
    }

    // ------------------------------------------------------------------
    // Enhanced selects (the select2-style dropdowns of the old directory,
    // rebuilt without jQuery): custom panel, search box on long lists,
    // keyboard support. The native select stays as the source of truth —
    // options are re-read every time the panel opens, so the category
    // cascade repopulating a select never leaves the panel stale.
    // ------------------------------------------------------------------
    var SEARCH_FROM = 8; // options; below this a search box is just noise

    function enhanceSelect(select) {
        if (!select || select.dataset.wdEnhanced) {
            return;
        }
        select.dataset.wdEnhanced = "1";
        select.classList.add("wd-select-native");

        var wrap = document.createElement("div");
        wrap.className = "wd-select";
        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(select);

        var toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "form-select text-start wd-select-toggle";
        toggle.setAttribute("aria-haspopup", "listbox");
        toggle.setAttribute("aria-expanded", "false");
        wrap.appendChild(toggle);

        var panel = document.createElement("div");
        panel.className = "wd-select-panel d-none";
        wrap.appendChild(panel);

        function label() {
            var option = select.options[select.selectedIndex];
            toggle.textContent = option ? option.textContent : "";
        }

        function close() {
            panel.classList.add("d-none");
            toggle.setAttribute("aria-expanded", "false");
        }

        function pick(value) {
            select.value = value;
            select.dispatchEvent(new Event("change", {bubbles: true}));
            label();
            close();
            toggle.focus();
        }

        function open() {
            panel.innerHTML = "";
            var options = Array.prototype.slice.call(select.options);
            var search = null;
            if (options.length >= SEARCH_FROM) {
                search = document.createElement("input");
                search.type = "text";
                search.className = "form-control form-control-sm wd-select-search";
                search.placeholder = "Buscar...";
                panel.appendChild(search);
            }
            var list = document.createElement("div");
            list.className = "wd-select-options";
            list.setAttribute("role", "listbox");
            panel.appendChild(list);

            function render(filter) {
                list.innerHTML = "";
                var visible = options.filter(function (option) {
                    return (
                        !option.disabled &&
                        (!filter ||
                            option.textContent
                                .toLowerCase()
                                .indexOf(filter.toLowerCase()) !== -1)
                    );
                });
                if (!visible.length) {
                    var empty = document.createElement("div");
                    empty.className = "wd-select-empty";
                    empty.textContent = "Sin resultados";
                    list.appendChild(empty);
                    return;
                }
                visible.forEach(function (option) {
                    var item = document.createElement("div");
                    item.className =
                        "wd-select-option" +
                        (option.value === select.value ? " active" : "");
                    item.setAttribute("role", "option");
                    item.textContent = option.textContent;
                    item.addEventListener("click", function () {
                        pick(option.value);
                    });
                    list.appendChild(item);
                });
            }

            render("");
            if (search) {
                search.addEventListener("input", function () {
                    render(search.value.trim());
                });
            }
            panel.classList.remove("d-none");
            toggle.setAttribute("aria-expanded", "true");
            if (search) {
                search.focus();
            }
        }

        toggle.addEventListener("click", function () {
            if (panel.classList.contains("d-none")) {
                open();
            } else {
                close();
            }
        });
        toggle.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                close();
            }
        });
        document.addEventListener("click", function (event) {
            if (!wrap.contains(event.target)) {
                close();
            }
        });
        select.addEventListener("change", label);
        label();
    }

    // ------------------------------------------------------------------
    // Zone filter: each option value is the target URL.
    // ------------------------------------------------------------------
    function initZoneSelect() {
        var select = byId("wd_zone_select");
        if (!select) {
            return;
        }
        select.addEventListener("change", function () {
            if (select.value) {
                window.location.href = select.value;
            }
        });
    }

    // ------------------------------------------------------------------
    // Cascading category filter (3 levels).
    // ------------------------------------------------------------------
    function findNode(nodes, id) {
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].id === id) {
                return nodes[i];
            }
        }
        return null;
    }

    function populateSelect(select, nodes) {
        while (select.options.length > 1) {
            select.remove(1);
        }
        nodes.forEach(function (node) {
            var option = document.createElement("option");
            option.value = node.id;
            option.textContent = node.name;
            select.appendChild(option);
        });
    }

    function showWrap(wrap, visible) {
        if (wrap) {
            wrap.classList.toggle("d-none", !visible);
        }
    }

    function initCategoryCascade() {
        var form = byId("wd_category_form");
        var l1 = byId("wd_cat_l1");
        var l2 = byId("wd_cat_l2");
        var l3 = byId("wd_cat_l3");
        if (!form || !l1 || !l2 || !l3) {
            return;
        }
        form.addEventListener("submit", function (event) {
            event.preventDefault();
        });

        // Restore the cascade for the currently selected category.
        var root = findNode(state.categories, state.selected[0]);
        if (root && root.children.length) {
            populateSelect(l2, root.children);
            showWrap(byId("wd_cat_l2_wrap"), true);
            if (state.selected[1]) {
                l2.value = String(state.selected[1]);
                var sub = findNode(root.children, state.selected[1]);
                if (sub && sub.children.length) {
                    populateSelect(l3, sub.children);
                    showWrap(byId("wd_cat_l3_wrap"), true);
                    if (state.selected[2]) {
                        l3.value = String(state.selected[2]);
                    }
                }
            }
        }

        l1.addEventListener("change", function () {
            var rootId = parseInt(l1.value, 10) || null;
            showWrap(byId("wd_cat_l2_wrap"), false);
            showWrap(byId("wd_cat_l3_wrap"), false);
            if (rootId) {
                var node = findNode(state.categories, rootId);
                if (node && node.children.length) {
                    populateSelect(l2, node.children);
                    showWrap(byId("wd_cat_l2_wrap"), true);
                }
            }
            fetchResults({category: rootId, page: 1});
        });

        l2.addEventListener("change", function () {
            var rootId = parseInt(l1.value, 10) || null;
            var subId = parseInt(l2.value, 10) || null;
            showWrap(byId("wd_cat_l3_wrap"), false);
            if (subId) {
                var rootNode = findNode(state.categories, rootId);
                var subNode = rootNode ? findNode(rootNode.children, subId) : null;
                if (subNode && subNode.children.length) {
                    populateSelect(l3, subNode.children);
                    showWrap(byId("wd_cat_l3_wrap"), true);
                }
            }
            fetchResults({category: subId || rootId, page: 1});
        });

        l3.addEventListener("change", function () {
            var leafId = parseInt(l3.value, 10) || null;
            var fallback = parseInt(l2.value, 10) || parseInt(l1.value, 10) || null;
            fetchResults({category: leafId || fallback, page: 1});
        });
    }

    // ------------------------------------------------------------------
    // Async text search.
    // ------------------------------------------------------------------
    function initAsyncSearch() {
        var form = byId("wd_search_form");
        var input = byId("wd_search_input");
        if (!form || !input) {
            return;
        }
        var timeout = null;
        input.addEventListener("input", function () {
            clearTimeout(timeout);
            var query = input.value.trim();
            if (query.length >= MIN_SEARCH_LENGTH) {
                timeout = setTimeout(function () {
                    fetchResults({search: query, page: 1});
                }, SEARCH_DELAY_MS);
            } else if (query.length === 0 && state.search) {
                fetchResults({search: "", page: 1});
            }
        });
        form.addEventListener("submit", function (event) {
            var query = input.value.trim();
            if (query.length >= MIN_SEARCH_LENGTH) {
                event.preventDefault();
                fetchResults({search: query, page: 1});
            }
        });
    }

    // ------------------------------------------------------------------
    // View type + page size toolbar.
    // ------------------------------------------------------------------
    function initToolbar() {
        document.querySelectorAll("[data-wd-view]").forEach(function (button) {
            button.addEventListener("click", function () {
                fetchResults({view: button.dataset.wdView, page: 1});
                updateToolbarButtons("[data-wd-view]", button);
            });
        });
        document.querySelectorAll("[data-wd-ppg]").forEach(function (button) {
            button.addEventListener("click", function () {
                fetchResults({ppg: parseInt(button.dataset.wdPpg, 10), page: 1});
                updateToolbarButtons("[data-wd-ppg]", button);
            });
        });
    }

    function updateToolbarButtons(selector, active) {
        document.querySelectorAll(selector).forEach(function (button) {
            button.className =
                button === active
                    ? "btn btn-sm btn-primary active"
                    : "btn btn-sm btn-outline-secondary";
        });
    }

    // ------------------------------------------------------------------
    // AJAX pagination (delegated: pager links are re-rendered).
    // ------------------------------------------------------------------
    function initPagination() {
        var results = byId("wd_results");
        if (!results) {
            return;
        }
        results.addEventListener("click", function (event) {
            var link = event.target.closest(".pagination a.page-link");
            if (!link) {
                return;
            }
            var href = link.getAttribute("href") || "";
            var match = href.match(/\/page\/(\d+)/) || href.match(/[?&]page=(\d+)/);
            event.preventDefault();
            fetchResults({page: match ? parseInt(match[1], 10) : 1});
        });
    }

    // ------------------------------------------------------------------
    // Shared AJAX fetch + URL update.
    // ------------------------------------------------------------------
    function buildQuery(params) {
        var query = new URLSearchParams();
        if (params.search) {
            query.set("search", params.search);
        }
        if (params.category) {
            query.set("category", params.category);
        }
        if (params.view !== "grid") {
            query.set("view", params.view);
        }
        if (params.ppg !== 21) {
            query.set("ppg", params.ppg);
        }
        if (params.page > 1) {
            query.set("page", params.page);
        }
        return query.toString();
    }

    function setLoading(loading) {
        state.loading = loading;
        var loader = byId("wd_category_loader");
        var searchLoader = byId("wd_search_loading");
        if (loader) {
            loader.classList.toggle("d-none", !loading);
        }
        if (searchLoader) {
            searchLoader.classList.toggle("d-none", !loading);
        }
    }

    function fetchResults(changes) {
        if (state.loading) {
            return;
        }
        Object.assign(state, changes);
        var query = buildQuery(state);
        setLoading(true);
        fetch("/comercio/ajax/search" + (query ? "?" + query : ""), {
            headers: {"X-Requested-With": "XMLHttpRequest"},
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("HTTP " + response.status);
                }
                return response.text();
            })
            .then(function (html) {
                var results = byId("wd_results");
                if (results) {
                    results.innerHTML = html;
                    results.scrollIntoView({behavior: "smooth", block: "start"});
                }
                if (window.history && window.history.pushState) {
                    window.history.pushState(
                        {},
                        document.title,
                        "/comercio" + (query ? "?" + query : "")
                    );
                }
                setLoading(false);
            })
            .catch(function () {
                // Network/server issue: fall back to a full page load.
                setLoading(false);
                window.location.href = "/comercio" + (query ? "?" + query : "");
            });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
