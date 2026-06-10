// Custom Searchable Select - Dropdown propio con búsqueda
// Sin dependencias externas, puro JavaScript + CSS

(function() {
    'use strict';
    
    function initCustomSelects() {
        if (!window.location.pathname.startsWith('/shop')) {
            return;
        }
        
        // Inicializar cuando el DOM esté listo
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setupSelects);
        } else {
            setupSelects();
        }
        
        // Reintentar después por si hay carga AJAX
        setTimeout(setupSelects, 500);
        setTimeout(setupSelects, 1500);
    }
    
    function setupSelects() {
        // Convertir selects de categorías
        var selects = document.querySelectorAll('#category-select-shop, #subcategory-select-shop');
        selects.forEach(function(select) {
            if (select.dataset.customSelect === 'initialized') return;
            
            convertToCustomSelect(select);
            select.dataset.customSelect = 'initialized';
        });
    }
    
    function convertToCustomSelect(originalSelect) {
        var parent = originalSelect.parentNode;
        var options = Array.from(originalSelect.options);
        var placeholder = originalSelect.getAttribute('data-placeholder') || 'Seleccionar...';
        var searchPlaceholder = originalSelect.getAttribute('data-search-placeholder') || 'Buscar...';
        
        // Crear contenedor
        var container = document.createElement('div');
        container.className = 'custom-searchable-select';
        
        // Crear trigger (botón visible)
        var trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'custom-select-trigger form-select text-start';
        trigger.innerHTML = '<span class="selected-text">' + getSelectedText(originalSelect) + '</span>' +
                           '<span class="dropdown-arrow">▼</span>';
        
        // Crear dropdown
        var dropdown = document.createElement('div');
        dropdown.className = 'custom-select-dropdown';
        
        // Crear input de búsqueda
        var searchBox = document.createElement('div');
        searchBox.className = 'custom-select-search';
        searchBox.innerHTML = '<input type="text" class="form-control" placeholder="' + searchPlaceholder + '" autocomplete="off">';
        
        // Crear lista de opciones
        var list = document.createElement('div');
        list.className = 'custom-select-options';
        
        options.forEach(function(option, index) {
            var item = document.createElement('div');
            item.className = 'custom-select-option';
            item.textContent = option.textContent;
            item.dataset.value = option.value;
            item.dataset.index = index;
            if (option.selected) item.classList.add('selected');
            list.appendChild(item);
        });
        
        // Armar estructura
        dropdown.appendChild(searchBox);
        dropdown.appendChild(list);
        container.appendChild(trigger);
        container.appendChild(dropdown);
        
        // Insertar y ocultar original
        parent.insertBefore(container, originalSelect);
        originalSelect.style.display = 'none';
        originalSelect.style.visibility = 'hidden';
        originalSelect.style.position = 'absolute';
        
        // Eventos
        trigger.addEventListener('click', function(e) {
            e.stopPropagation();
            closeAllDropdowns();
            dropdown.classList.toggle('show');
            if (dropdown.classList.contains('show')) {
                searchBox.querySelector('input').focus();
            }
        });
        
        // Búsqueda en tiempo real
        var searchInput = searchBox.querySelector('input');
        searchInput.addEventListener('input', function() {
            var term = this.value.toLowerCase();
            var items = list.querySelectorAll('.custom-select-option');
            items.forEach(function(item) {
                var text = item.textContent.toLowerCase();
                item.style.display = text.includes(term) ? '' : 'none';
            });
        });
        
        // Selección de opción
        list.addEventListener('click', function(e) {
            if (e.target.classList.contains('custom-select-option')) {
                var value = e.target.dataset.value;
                var text = e.target.textContent;
                
                // Actualizar select original
                originalSelect.value = value;
                trigger.querySelector('.selected-text').textContent = text;
                
                // Actualizar clases
                list.querySelectorAll('.custom-select-option').forEach(function(opt) {
                    opt.classList.remove('selected');
                });
                e.target.classList.add('selected');
                
                // Cerrar dropdown
                dropdown.classList.remove('show');
                
                // Disparar cambio
                var event = new Event('change');
                originalSelect.dispatchEvent(event);
                
                // Redirigir si es URL
                if (value && value.startsWith('/')) {
                    window.location.href = value;
                }
            }
        });
        
        // Cerrar al hacer click fuera
        document.addEventListener('click', function(e) {
            if (!container.contains(e.target)) {
                dropdown.classList.remove('show');
            }
        });
    }
    
    function getSelectedText(select) {
        var selected = select.options[select.selectedIndex];
        return selected ? selected.textContent : 'Seleccionar...';
    }
    
    function closeAllDropdowns() {
        document.querySelectorAll('.custom-select-dropdown.show').forEach(function(d) {
            d.classList.remove('show');
        });
    }
    
    initCustomSelects();
})();
