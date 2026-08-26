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
        // The page's own path (/comercio or /comercio/zona/<key>) and zone:
        // every AJAX refresh stays on that path and asks the server for
        // that zone, so a visitor on /comercio/zona/guanarteme does not get
        // widened to the whole archipelago by the first filter they touch.
        baseUrl: "/comercio",
        zone: "canarias",
    };

    var DEFAULT_BASE_URL = "/comercio";
    var DEFAULT_ZONE = "canarias";
    var AJAX_URL = "/comercio/ajax/search";

    var MIN_SEARCH_LENGTH = 3;
    var SEARCH_DELAY_MS = 400;

    function byId(id) {
        return document.getElementById(id);
    }

    // Query string params outside this module's own known set (search,
    // category, view, ppg, page): whatever a bridge module's filter put
    // there (facility=1,2 / certification=sustainability / ...).
    var KNOWN_PARAMS = ["search", "category", "view", "ppg", "page"];

    function currentExtraParams() {
        var extra = {};
        new URLSearchParams(window.location.search).forEach(function (
            value,
            key
        ) {
            if (KNOWN_PARAMS.indexOf(key) === -1) {
                extra[key] = value;
            }
        });
        return extra;
    }

    // ------------------------------------------------------------------
    // Turn a server-built filter URL (a select option's value, a chip's
    // href, a pill's "remove" link) into a fetchResults() call instead of
    // a full navigation. The URL already encodes the COMPLETE target state
    // -- every bridge filter builds it that way precisely so a click never
    // drops a sibling filter -- so re-deriving `changes` from its query
    // string is enough: known params are read directly, and anything else
    // (facility, certification, whatever a future bridge adds) replaces
    // `state.extra` wholesale, which both adds a fresh one and drops one
    // the visitor just turned off.
    // ------------------------------------------------------------------
    function changesFromQuery(query) {
        var params = new URLSearchParams(query);
        var changes = {extra: {}};
        params.forEach(function (value, key) {
            if (KNOWN_PARAMS.indexOf(key) === -1) {
                changes.extra[key] = value;
            }
        });
        changes.search = params.get("search") || "";
        var category = params.get("category");
        changes.category = category ? parseInt(category, 10) || null : null;
        changes.view = params.get("view") || "grid";
        changes.ppg = parseInt(params.get("ppg"), 10) || 21;
        // A filter change always starts back at page 1: the answer's size
        // changed, so the old page number rarely still means anything.
        changes.page = 1;
        return changes;
    }

    // Only the query string is read: the pathname of a filter link is the
    // page's own base URL (the server builds every filter URL on
    // `base_url`), which fetchResults() already keeps through pushState.
    function followFilterUrl(url) {
        var queryIndex = url.indexOf("?");
        var query = queryIndex === -1 ? "" : url.slice(queryIndex + 1);
        fetchResults(changesFromQuery(query));
    }

    // The page address for the current filter state: the page's own
    // pathname (never a bare /comercio when the visitor is on a zone path)
    // plus the query string.
    function pageUrl(query) {
        return state.baseUrl + (query ? "?" + query : "");
    }

    function ajaxUrl(query) {
        var params = new URLSearchParams(query);
        if (state.zone && state.zone !== DEFAULT_ZONE) {
            params.set("zone", state.zone);
        }
        var serialized = params.toString();
        return AJAX_URL + (serialized ? "?" + serialized : "");
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
        state.baseUrl = dataNode.dataset.baseUrl || DEFAULT_BASE_URL;
        state.zone = dataNode.dataset.zone || DEFAULT_ZONE;
        state.category =
            state.selected[2] || state.selected[1] || state.selected[0] || null;
        // Every query string param this base module does not itself manage
        // (bridge modules' "facility", "certification", and whatever comes
        // next) is carried verbatim through every AJAX round trip below, so
        // ticking a category or typing a search never silently drops a
        // filter a bridge module added. Read once, at load, from the address
        // bar that rendered this exact page: it already reflects every
        // active filter, managed or not.
        state.extra = currentExtraParams();

        initSidebar();
        initAsyncSearch();
        initToolbar();
        initPagination();
        initFilterLinks();
    }

    // ------------------------------------------------------------------
    // Everything living inside #wd_sidebar: the zone select, the category
    // cascade, and whatever a bridge module (certification, facilities)
    // added to the extension hook. Re-run after every AJAX round trip that
    // swaps this whole block in fresh, not just at page load -- a select's
    // 'change' listener and the enhanced-dropdown wrapper both attach to
    // ONE specific DOM node, which the swap just replaced with a new one
    // that has neither yet.
    // ------------------------------------------------------------------
    function initSidebar() {
        initZoneSelect();
        initNavSelects();
        initCategoryCascade();
        ["wd_zone_select", "wd_cat_l1", "wd_cat_l2", "wd_cat_l3"].forEach(
            function (id) {
                enhanceSelect(byId(id));
            }
        );
    }

    // ------------------------------------------------------------------
    // Navigation selects: any select marked wd-nav-select follows the
    // picked option's value through the same AJAX pipeline as the category
    // cascade, instead of a full page navigation. The generic hook the
    // sidebar bridges (the facilities filter, and whatever comes next)
    // build on: the server renders the URLs, this only follows them --
    // async now, so ticking "Rampa de acceso" no longer reloads the page
    // out from under a category the visitor already picked (reported
    // 2026-08-21).
    // ------------------------------------------------------------------
    function initNavSelects() {
        document
            .querySelectorAll("select.wd-nav-select")
            .forEach(function (select) {
                select.addEventListener("change", function () {
                    if (select.value) {
                        followFilterUrl(select.value);
                    }
                });
                enhanceSelect(select);
            });
    }

    // ------------------------------------------------------------------
    // Filter chip / pill links: any anchor marked wd-filter-link (the
    // certification chips, the facilities "Quitar"/pill remove buttons, the
    // active-filters summary at the top) follows its href through the same
    // AJAX pipeline. Delegated on #wrap so chips re-rendered by an AJAX
    // response (a fresh sidebar, a fresh summary bar) are wired without
    // re-scanning the DOM after every fetch.
    // ------------------------------------------------------------------
    function initFilterLinks() {
        var wrap = byId("wrap");
        if (!wrap) {
            return;
        }
        wrap.addEventListener("click", function (event) {
            var link = event.target.closest("a.wd-filter-link");
            if (!link) {
                return;
            }
            event.preventDefault();
            followFilterUrl(link.getAttribute("href"));
        });
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
    // Zone filter: each option value is the target URL, built server-side
    // with every active filter already in its query string. A real
    // navigation, not an AJAX call: the zone is the page's path.
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

        // The server-rendered selection wins over the copy read at page
        // load: after an AJAX swap the old copy is stale (a chip that just
        // cleared the category would otherwise re-select its subcategory).
        if (form.dataset.selected) {
            try {
                state.selected = JSON.parse(form.dataset.selected);
            } catch (error) {
                // Keep the previous selection.
            }
        }
        state.category =
            state.selected[2] || state.selected[1] || state.selected[0] || null;

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
        Object.keys(params.extra || {}).forEach(function (key) {
            if (params.extra[key]) {
                query.set(key, params.extra[key]);
            }
        });
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
        fetch(ajaxUrl(query), {
            headers: {"X-Requested-With": "XMLHttpRequest"},
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("HTTP " + response.status);
                }
                return response.text();
            })
            .then(function (html) {
                // The AJAX response carries two named blocks (results AND a
                // fresh sidebar) in one response body; pull each out by id
                // and inject into its own live container. A bridge filter's
                // chip has to show its own new active/inactive state after
                // this round trip, same as the category cascade already
                // does client-side -- re-rendering the whole sidebar is
                // simpler than teaching every bridge chip to track that in
                // JS, and this is the one place that pays for it.
                var doc = new DOMParser().parseFromString(html, "text/html");
                var resultsSource = doc.getElementById("wd_ajax_results");
                var sidebarSource = doc.getElementById("wd_ajax_sidebar");
                var results = byId("wd_results");
                if (results && resultsSource) {
                    results.innerHTML = resultsSource.innerHTML;
                    results.scrollIntoView({behavior: "smooth", block: "start"});
                }
                var sidebar = byId("wd_sidebar");
                if (sidebar && sidebarSource) {
                    sidebar.innerHTML = sidebarSource.innerHTML;
                    initSidebar();
                }
                if (window.history && window.history.pushState) {
                    window.history.pushState({}, document.title, pageUrl(query));
                }
                setLoading(false);
            })
            .catch(function () {
                // Network/server issue: fall back to a full page load.
                setLoading(false);
                window.location.href = pageUrl(query);
            });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
