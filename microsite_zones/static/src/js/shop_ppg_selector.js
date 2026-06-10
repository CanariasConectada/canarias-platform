// Selector de productos por página
document.addEventListener('DOMContentLoaded', function() {
    // Verificar si estamos en la página de shop
    if (!document.querySelector('#products_grid')) return;
    
    // Obtener el valor actual de ppg de la URL
    const urlParams = new URLSearchParams(window.location.search);
    let currentPpg = parseInt(urlParams.get('ppg')) || 21;
    
    // Función para actualizar URL
    function updateUrlPpg(ppg) {
        const url = new URL(window.location.href);
        url.searchParams.set('ppg', ppg);
        url.searchParams.set('page', '1');
        return url.toString();
    }
    
    // Crear el selector HTML
    const selectorDiv = document.createElement('div');
    selectorDiv.className = 'o_wsale_ppg_bar d-flex align-items-center gap-2 ms-auto';
    selectorDiv.innerHTML = '<label class="text-muted small mb-0">Mostrar:</label><div class="btn-group" role="group" aria-label="Productos por página"><a href="' + updateUrlPpg(12) + '" class="btn btn-sm ' + (currentPpg === 12 ? 'btn-primary active' : 'btn-outline-secondary') + '">12</a><a href="' + updateUrlPpg(24) + '" class="btn btn-sm ' + (currentPpg === 24 ? 'btn-primary active' : 'btn-outline-secondary') + '">24</a><a href="' + updateUrlPpg(48) + '" class="btn btn-sm ' + (currentPpg === 48 ? 'btn-primary active' : 'btn-outline-secondary') + '">48</a><a href="' + updateUrlPpg(96) + '" class="btn btn-sm ' + (currentPpg === 96 ? 'btn-primary active' : 'btn-outline-secondary') + '">96</a></div>';
    
    // Insertar en el header de productos
    const header = document.querySelector('#o_wsale_products_header');
    if (header) {
        header.appendChild(selectorDiv);
    }
});
