/**
 * Searchable Category Select for Microsites
 * Basado en el patrón del Directorio - Implementación vanilla JS
 * 
 * Este script transforma un select estándar en un dropdown searchable
 * sin dependencias externas (no jQuery, no Select2)
 */

(function() {
    'use strict';
    
    // Namespace para evitar conflictos
    var MicrositeSearchable = {
        initialized: false,
        
        init: function() {
            if (this.initialized) return;
            this.initialized = true;
            
            console.log('[MicrositeSearchable] Inicializando...');
            this.initCategorySelects();
        },
        
        /**
         * Inicializa todos los selects de categoría que aún no han sido mejorados
         */
        initCategorySelects: function() {
            var selects = document.querySelectorAll('.microsite-cat-select:not([data-searchable="true"])');
            
            console.log('[MicrositeSearchable] Encontrados ' + selects.length + ' selects para mejorar');
            
            selects.forEach(function(select) {
                this.enhanceSelect(select);
            }.bind(this));
        },
        
        /**
         * Mejora un select individual con funcionalidad de búsqueda
         */
        enhanceSelect: function(select) {
            // Marcar como procesado
            select.dataset.searchable = 'true';
            
            var isInSidebar = select.closest('#products_grid_before') !== null;
            var form = select.closest('form');
            
            console.log('[MicrositeSearchable] Mejorando select:', select.id || 'sin-id', 'en sidebar:', isInSidebar);
            
            // Crear wrapper principal
            var wrapper = document.createElement('div');
            wrapper.className = 'microsite-searchable-wrapper';
            wrapper.style.cssText = 'position:relative;display:block;z-index:9999;width:100%;';
            
            // Asegurar que el contenedor padre tenga overflow visible
            var parentCard = select.closest('.card-body');
            if (parentCard) {
                parentCard.style.overflow = 'visible';
            }
            
            // Crear botón toggle (muestra la opción seleccionada)
            var toggle = document.createElement('button');
            toggle.type = 'button';
            toggle.className = 'form-select text-start microsite-searchable-toggle';
            
            var selectedOption = select.options[select.selectedIndex];
            var selectedText = selectedOption ? selectedOption.text : 'Seleccione categoría...';
            toggle.innerHTML = '<span class="selected-text">' + this.escapeHtml(selectedText) + '</span>';
            toggle.style.cssText = 'position:relative;width:100%;background:#fff;text-align:left;';
            
            // Crear dropdown
            var dropdown = document.createElement('div');
            dropdown.className = 'microsite-searchable-dropdown';
            dropdown.style.cssText = [
                'position:absolute',
                'z-index:99999',
                'background:#fff',
                'border:1px solid #ced4da',
                'border-radius:0.375rem',
                'width:100%',
                'max-height:300px',
                'overflow:hidden',
                'display:none',
                'box-shadow:0 0.5rem 1rem rgba(0,0,0,0.15)',
                'top:100%',
                'left:0',
                'margin-top:2px'
            ].join(';');
            
            // Crear input de búsqueda
            var searchContainer = document.createElement('div');
            searchContainer.className = 'p-2 border-bottom';
            searchContainer.innerHTML = '<input type="text" class="form-control form-control-sm" placeholder="Buscar categoría..." autocomplete="off">';
            var searchInput = searchContainer.querySelector('input');
            
            // Crear lista de opciones
            var list = document.createElement('div');
            list.className = 'microsite-searchable-options';
            list.style.cssText = 'max-height:220px;overflow-y:auto;-webkit-overflow-scrolling:touch;';
            
            // Construir opciones desde el select original
            Array.from(select.options).forEach(function(opt, index) {
                var item = document.createElement('div');
                item.className = 'microsite-searchable-option';
                if (index === 0) item.classList.add('text-muted');
                item.textContent = opt.text;
                item.dataset.value = opt.value;
                item.style.cssText = 'padding:8px 12px;cursor:pointer;transition:background 0.15s;font-size:14px;border-bottom:1px solid #f0f0f0;';
                
                // Hover effect
                item.addEventListener('mouseenter', function() {
                    this.style.background = '#e9ecef';
                });
                item.addEventListener('mouseleave', function() {
                    this.style.background = 'transparent';
                });
                
                // Click para seleccionar
                item.addEventListener('click', function(e) {
                    e.stopPropagation();
                    
                    // Actualizar valor del select original
                    select.value = opt.value;
                    
                    // Actualizar texto del toggle
                    toggle.querySelector('.selected-text').textContent = opt.text;
                    
                    // Cerrar dropdown
                    dropdown.style.display = 'none';
                    
                    // Marcar opción como activa visualmente
                    list.querySelectorAll('.microsite-searchable-option').forEach(function(optEl) {
                        optEl.style.background = 'transparent';
                        optEl.style.fontWeight = 'normal';
                    });
                    item.style.background = '#714B67';
                    item.style.color = '#fff';
                    
                    // Submit del formulario si existe
                    if (form) {
                        console.log('[MicrositeSearchable] Submit form con categoría:', opt.value);
                        form.submit();
                    }
                });
                
                list.appendChild(item);
            });
            
            // Funcionalidad de búsqueda
            searchInput.addEventListener('input', function() {
                var term = this.value.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                var hasResults = false;
                
                list.querySelectorAll('.microsite-searchable-option').forEach(function(item) {
                    var text = item.textContent.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                    var matches = text.includes(term);
                    item.style.display = matches ? 'block' : 'none';
                    if (matches) hasResults = true;
                });
                
                // Mostrar mensaje si no hay resultados
                var noResultsMsg = list.querySelector('.no-results-msg');
                if (!hasResults) {
                    if (!noResultsMsg) {
                        noResultsMsg = document.createElement('div');
                        noResultsMsg.className = 'no-results-msg text-muted text-center py-3';
                        noResultsMsg.textContent = 'No se encontraron categorías';
                        list.appendChild(noResultsMsg);
                    }
                    noResultsMsg.style.display = 'block';
                } else if (noResultsMsg) {
                    noResultsMsg.style.display = 'none';
                }
            });
            
            // Posicionamiento inteligente del dropdown
            var positionDropdown = function() {
                var rect = toggle.getBoundingClientRect();
                var viewportHeight = window.innerHeight;
                var dropdownHeight = Math.min(300, list.scrollHeight + 60);
                var spaceBelow = viewportHeight - rect.bottom;
                
                if (spaceBelow < dropdownHeight && rect.top > dropdownHeight) {
                    // Mostrar arriba
                    dropdown.style.top = 'auto';
                    dropdown.style.bottom = '100%';
                    dropdown.style.marginTop = '0';
                    dropdown.style.marginBottom = '4px';
                } else {
                    // Mostrar abajo (default)
                    dropdown.style.top = '100%';
                    dropdown.style.bottom = 'auto';
                    dropdown.style.marginTop = '2px';
                    dropdown.style.marginBottom = '0';
                }
            };
            
            // Toggle del dropdown
            toggle.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                var isOpen = dropdown.style.display === 'block';
                
                // Cerrar otros dropdowns abiertos
                document.querySelectorAll('.microsite-searchable-dropdown').forEach(function(d) {
                    if (d !== dropdown) d.style.display = 'none';
                });
                
                if (!isOpen) {
                    positionDropdown();
                    dropdown.style.display = 'block';
                    searchInput.value = '';
                    searchInput.focus();
                    
                    // Resetear búsqueda
                    list.querySelectorAll('.microsite-searchable-option').forEach(function(item) {
                        item.style.display = 'block';
                    });
                    var noResultsMsg = list.querySelector('.no-results-msg');
                    if (noResultsMsg) noResultsMsg.style.display = 'none';
                } else {
                    dropdown.style.display = 'none';
                }
            });
            
            // Cerrar al hacer click fuera
            document.addEventListener('click', function(e) {
                if (!dropdown.contains(e.target) && e.target !== toggle) {
                    dropdown.style.display = 'none';
                }
            });
            
            // Prevenir cierre al hacer click dentro del dropdown
            dropdown.addEventListener('click', function(e) {
                if (e.target !== searchInput) e.stopPropagation();
            });
            
            // Reposicionar en resize
            window.addEventListener('resize', function() {
                if (dropdown.style.display === 'block') {
                    positionDropdown();
                }
            }, { passive: true });
            
            // Ensamblar componente
            dropdown.appendChild(searchContainer);
            dropdown.appendChild(list);
            wrapper.appendChild(dropdown);
            wrapper.appendChild(toggle);
            
            // Insertar wrapper y ocultar select original
            select.style.display = 'none';
            select.parentNode.insertBefore(wrapper, select);
            wrapper.appendChild(select);
            
            console.log('[MicrositeSearchable] Select mejorado correctamente');
        },
        
        /**
         * Escapa HTML para evitar XSS
         */
        escapeHtml: function(text) {
            var div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    };
    
    // Inicializar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            MicrositeSearchable.init();
        });
    } else {
        // DOM ya está listo
        MicrositeSearchable.init();
    }
    
    // También exponer para llamadas manuales si es necesario
    window.MicrositeSearchable = MicrositeSearchable;
    
})();
