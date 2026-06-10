/**
 * ZCA Directorio — Frontend JS
 * AJAX search, cascading filters, debounce, grid/list toggle, pagination, pushState
 */

(function () {
    'use strict';

    // ----------------------------------------------------------------
    // Utilities
    // ----------------------------------------------------------------
    function debounce(fn, delay) {
        var timer;
        return function () {
            var args = arguments;
            var ctx = this;
            clearTimeout(timer);
            timer = setTimeout(function () {
                fn.apply(ctx, args);
            }, delay);
        };
    }

    function getParam(name) {
        var url = new URL(window.location.href);
        return url.searchParams.get(name) || '';
    }

    function buildQueryString(params) {
        var parts = [];
        Object.keys(params).forEach(function (key) {
            if (params[key] !== undefined && params[key] !== null && params[key] !== '') {
                parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(params[key]));
            }
        });
        return parts.join('&');
    }

    // ----------------------------------------------------------------
    // State
    // ----------------------------------------------------------------
    var state = {
        zone: getParam('zone'),
        tipo: getParam('tipo'),
        category: getParam('category'),
        subcategory: getParam('subcategory'),
        search: getParam('search'),
        view: localStorage.getItem('zca_dir_view') || getParam('view') || 'grid',
        ppg: parseInt(getParam('ppg')) || 21,
        page: parseInt(getParam('page')) || 1,
    };

    // Category tree injected by template
    var categoryTree = (window.ZCA_DIR_DATA && window.ZCA_DIR_DATA.categoryTree) ? window.ZCA_DIR_DATA.categoryTree : {};

    // ----------------------------------------------------------------
    // DOM refs
    // ----------------------------------------------------------------
    var resultsContainer = document.getElementById('zca-dir-results');
    var zoneSelect       = document.getElementById('zca-filter-zone');
    var tipoSelect       = document.getElementById('zca-filter-tipo');
    var catSelect        = document.getElementById('zca-filter-cat');
    var subcatSelect     = document.getElementById('zca-filter-subcat');
    var searchInput      = document.getElementById('zca-filter-search');
    var heroSearchInput  = document.getElementById('zca-search-input');
    var viewBtns         = document.querySelectorAll('.zca-view-btn');
    var filterForm       = document.getElementById('zca-filter-form');

    // ----------------------------------------------------------------
    // Core AJAX search
    // ----------------------------------------------------------------
    function performCategoryAjaxSearch(overrides, pushUrl) {
        var params = Object.assign({}, state, overrides || {});

        // Never send empty keys
        var clean = {};
        ['zone', 'tipo', 'category', 'subcategory', 'search', 'view', 'ppg', 'page'].forEach(function (k) {
            if (params[k] !== '' && params[k] !== null && params[k] !== undefined) {
                clean[k] = params[k];
            }
        });

        var qs = buildQueryString(clean);
        var ajaxUrl = '/directorio/ajax/search' + (qs ? '?' + qs : '');
        var historyUrl = '/directorio' + (qs ? '?' + qs : '');

        // Set loading state
        if (resultsContainer) {
            resultsContainer.classList.add('zca-loading');
            var spinner = document.createElement('div');
            spinner.className = 'zca-spinner active';
            spinner.innerHTML = '<i class="fa fa-spinner fa-spin"></i>';
            var inner = resultsContainer.querySelector('.container');
            if (inner) inner.style.opacity = '0.4';
        }

        // Update state
        Object.assign(state, params);

        fetch(ajaxUrl, {
            method: 'GET',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
        .then(function (resp) {
            if (!resp.ok) throw new Error('Network response was not ok');
            return resp.text();
        })
        .then(function (html) {
            if (resultsContainer) {
                var inner = resultsContainer.querySelector('.container');
                if (inner) {
                    inner.innerHTML = html;
                    inner.style.opacity = '1';
                } else {
                    resultsContainer.innerHTML = '<div class="container">' + html + '</div>';
                }
                resultsContainer.classList.remove('zca-loading');
            }

            // Bind new pagination links
            bindPaginationLinks();

            // Push URL
            if (pushUrl !== false) {
                window.history.pushState({ zcaState: clean }, '', historyUrl);
            }

            // Scroll to results
            if (resultsContainer) {
                var top = resultsContainer.getBoundingClientRect().top + window.scrollY - 80;
                window.scrollTo({ top: top, behavior: 'smooth' });
            }
        })
        .catch(function (err) {
            console.error('[ZCA] AJAX error:', err);
            if (resultsContainer) {
                resultsContainer.classList.remove('zca-loading');
                var inner = resultsContainer.querySelector('.container');
                if (inner) inner.style.opacity = '1';
            }
        });
    }

    // ----------------------------------------------------------------
    // Cascading category selects
    // ----------------------------------------------------------------
    function populateSelect(selectEl, options, selectedVal) {
        if (!selectEl) return;
        // Clear all options except the first placeholder
        while (selectEl.options.length > 1) {
            selectEl.remove(1);
        }
        options.forEach(function (opt) {
            var el = document.createElement('option');
            el.value = opt.value;
            el.textContent = opt.label;
            if (opt.value === selectedVal) el.selected = true;
            selectEl.appendChild(el);
        });
    }

    function updateCatSelect(tipoVal, selectedCat) {
        var cats = [];
        if (tipoVal && categoryTree[tipoVal]) {
            var catMap = categoryTree[tipoVal].categorias || {};
            Object.keys(catMap).forEach(function (k) {
                cats.push({ value: k, label: catMap[k].label || k });
            });
        }
        populateSelect(catSelect, cats, selectedCat || '');
        updateSubcatSelect(tipoVal, catSelect ? catSelect.value : '', '');
    }

    function updateSubcatSelect(tipoVal, catVal, selectedSubcat) {
        var subcats = [];
        if (tipoVal && catVal && categoryTree[tipoVal] &&
            categoryTree[tipoVal].categorias && categoryTree[tipoVal].categorias[catVal]) {
            var arr = categoryTree[tipoVal].categorias[catVal].subcategorias || [];
            arr.forEach(function (s) {
                subcats.push({ value: s, label: s });
            });
        }
        populateSelect(subcatSelect, subcats, selectedSubcat || '');
    }

    // ----------------------------------------------------------------
    // Event bindings
    // ----------------------------------------------------------------
    function bindFilters() {
        if (zoneSelect) {
            zoneSelect.addEventListener('change', function () {
                state.zone = this.value;
                state.page = 1;
                performCategoryAjaxSearch();
            });
        }

        if (tipoSelect) {
            tipoSelect.addEventListener('change', function () {
                state.tipo = this.value;
                state.category = '';
                state.subcategory = '';
                state.page = 1;
                updateCatSelect(state.tipo, '');
                performCategoryAjaxSearch();
            });
        }

        if (catSelect) {
            catSelect.addEventListener('change', function () {
                state.category = this.value;
                state.subcategory = '';
                state.page = 1;
                updateSubcatSelect(state.tipo, state.category, '');
                performCategoryAjaxSearch();
            });
        }

        if (subcatSelect) {
            subcatSelect.addEventListener('change', function () {
                state.subcategory = this.value;
                state.page = 1;
                performCategoryAjaxSearch();
            });
        }

        // Text search with debounce (min 3 chars or empty)
        var debouncedSearch = debounce(function (val) {
            if (val.length === 0 || val.length >= 3) {
                state.search = val;
                state.page = 1;
                performCategoryAjaxSearch();
            }
        }, 400);

        if (searchInput) {
            searchInput.addEventListener('input', function () {
                debouncedSearch(this.value.trim());
            });
        }

        // Hero search override: intercept form submit
        if (heroSearchInput) {
            var heroForm = heroSearchInput.closest('form');
            if (heroForm) {
                heroForm.addEventListener('submit', function (e) {
                    var val = heroSearchInput.value.trim();
                    if (val.length >= 3 || val.length === 0) {
                        e.preventDefault();
                        state.search = val;
                        state.page = 1;
                        // Update the filter input if exists
                        if (searchInput) searchInput.value = val;
                        performCategoryAjaxSearch();
                    }
                });
            }
        }

        // Prevent default filter form submit (use AJAX instead)
        if (filterForm) {
            filterForm.addEventListener('submit', function (e) {
                e.preventDefault();
                state.search = searchInput ? searchInput.value.trim() : '';
                state.zone = zoneSelect ? zoneSelect.value : '';
                state.tipo = tipoSelect ? tipoSelect.value : '';
                state.category = catSelect ? catSelect.value : '';
                state.subcategory = subcatSelect ? subcatSelect.value : '';
                state.page = 1;
                performCategoryAjaxSearch();
            });
        }
    }

    function bindViewToggle() {
        viewBtns.forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                var v = this.getAttribute('data-view') || 'grid';
                state.view = v;
                state.page = 1;
                localStorage.setItem('zca_dir_view', v);
                // Update active class immediately
                viewBtns.forEach(function (b) { b.classList.remove('active'); });
                this.classList.add('active');
                performCategoryAjaxSearch();
            });
        });
    }

    function bindPaginationLinks() {
        var container = resultsContainer || document;
        var pageLinks = container.querySelectorAll('.zca-page-btn[data-page]');
        pageLinks.forEach(function (link) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                var p = this.getAttribute('data-page');
                if (p === 'prev') {
                    state.page = Math.max(1, state.page - 1);
                } else if (p === 'next') {
                    state.page = state.page + 1;
                } else if (p && !isNaN(parseInt(p))) {
                    state.page = parseInt(p);
                } else {
                    return; // ellipsis or invalid
                }
                performCategoryAjaxSearch();
            });
        });

        // PPG selector links inside results
        var ppgBtns = container.querySelectorAll('.zca-ppg-btn');
        ppgBtns.forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                var ppgVal = parseInt(this.textContent.trim());
                if (!isNaN(ppgVal)) {
                    state.ppg = ppgVal;
                    state.page = 1;
                    ppgBtns.forEach(function (b) { b.classList.remove('active'); });
                    this.classList.add('active');
                    performCategoryAjaxSearch();
                }
            });
        });
    }

    // ----------------------------------------------------------------
    // "Leer más" toggle for microsite historia
    // ----------------------------------------------------------------
    function bindReadMore() {
        document.querySelectorAll('.zca-read-more').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var targetId = this.getAttribute('data-target');
                var textWrap = targetId
                    ? document.getElementById(targetId)
                    : this.previousElementSibling;
                if (!textWrap) return;
                var wrap = textWrap.closest('.zca-ms-historia__text-wrap') || textWrap.parentElement;
                if (wrap.classList.contains('expanded')) {
                    wrap.classList.remove('expanded');
                    this.innerHTML = 'Leer más <i class="fa fa-chevron-down"></i>';
                } else {
                    wrap.classList.add('expanded');
                    this.innerHTML = 'Leer menos <i class="fa fa-chevron-up"></i>';
                }
            });
        });
    }

    // ----------------------------------------------------------------
    // Microsite contact form (AJAX)
    // ----------------------------------------------------------------
    function bindContactForm() {
        var form = document.getElementById('zca-contact-form');
        var feedback = document.getElementById('zca-form-feedback');
        if (!form || !feedback) return;

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var submitBtn = form.querySelector('[type="submit"]');
            if (submitBtn) submitBtn.disabled = true;

            var data = new FormData(form);
            var payload = {};
            data.forEach(function (v, k) { payload[k] = v; });

            // Use Odoo's /web/dataset/call_kw to create a CRM lead or a simple mail
            var leadPayload = {
                jsonrpc: '2.0',
                method: 'call',
                id: Date.now(),
                params: {
                    model: 'mail.message',
                    method: 'create',
                    args: [{
                        subject: 'Contacto web: ' + (payload.name || ''),
                        body: '<p><b>Nombre:</b> ' + (payload.name || '') + '</p>'
                              + '<p><b>Email:</b> ' + (payload.email || '') + '</p>'
                              + '<p><b>Teléfono:</b> ' + (payload.phone || '') + '</p>'
                              + '<p><b>Mensaje:</b> ' + (payload.message || '') + '</p>',
                        message_type: 'email',
                        res_id: parseInt(payload.partner_id) || 0,
                        model: 'res.partner',
                    }],
                    kwargs: {},
                },
            };

            fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify(leadPayload),
            })
            .then(function (resp) { return resp.json(); })
            .then(function (result) {
                if (result.error) {
                    throw new Error(result.error.data && result.error.data.message || 'Error al enviar');
                }
                feedback.textContent = '¡Mensaje enviado! Nos pondremos en contacto pronto.';
                feedback.className = 'zca-form-feedback success';
                form.reset();
            })
            .catch(function (err) {
                feedback.textContent = 'Error al enviar el mensaje. Por favor, inténtelo de nuevo.';
                feedback.className = 'zca-form-feedback error';
                console.error('[ZCA] Contact form error:', err);
            })
            .finally(function () {
                if (submitBtn) submitBtn.disabled = false;
            });
        });
    }

    // ----------------------------------------------------------------
    // Browser back/forward (popstate)
    // ----------------------------------------------------------------
    window.addEventListener('popstate', function (e) {
        if (e.state && e.state.zcaState) {
            Object.assign(state, e.state.zcaState);
            performCategoryAjaxSearch(null, false);
        }
    });

    // ----------------------------------------------------------------
    // Init: apply saved view from localStorage immediately
    // ----------------------------------------------------------------
    function applyInitialView() {
        var savedView = localStorage.getItem('zca_dir_view');
        if (savedView && savedView !== state.view) {
            state.view = savedView;
            // Toggle active btn
            viewBtns.forEach(function (b) {
                b.classList.toggle('active', b.getAttribute('data-view') === savedView);
            });
            // Toggle grid class
            var grid = document.getElementById('zca-cards-container');
            if (grid) {
                if (savedView === 'list') {
                    grid.classList.add('zca-cards-grid--list');
                } else {
                    grid.classList.remove('zca-cards-grid--list');
                }
            }
        }
        // Populate cascading selects from current state
        if (categoryTree && Object.keys(categoryTree).length > 0) {
            updateCatSelect(state.tipo, state.category);
            updateSubcatSelect(state.tipo, state.category, state.subcategory);
        }
    }

    // ----------------------------------------------------------------
    // DOMContentLoaded
    // ----------------------------------------------------------------
    document.addEventListener('DOMContentLoaded', function () {
        applyInitialView();
        bindFilters();
        bindViewToggle();
        bindPaginationLinks();
        bindReadMore();
        bindContactForm();
    });

})();
