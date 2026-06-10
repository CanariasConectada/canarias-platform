// Toolbar y ajustes del shop
document.addEventListener('DOMContentLoaded', function() {
    const toolbar = document.getElementById('shop-directory-toolbar');
    const container = document.getElementById('o_wsale_container');
    const grid = document.getElementById('o_wsale_products_grid');
    
    // MOVER TOOLBAR
    if (toolbar && container) {
        const firstChild = container.firstChild;
        if (firstChild) {
            container.insertBefore(toolbar, firstChild);
        }
    }
    
    // ICONO A CATEGORÍAS
    const categoryTitles = document.querySelectorAll('.o_categories_collapse_title b, .products_categories .accordion-button b');
    categoryTitles.forEach(function(title) {
        if (title.textContent.includes('Categorías') && !title.querySelector('i')) {
            const icon = document.createElement('i');
            icon.className = 'fa fa-tags';
            icon.style.color = '#714B67';
            icon.style.marginRight = '0.5rem';
            title.insertBefore(icon, title.firstChild);
        }
    });
    
    // VISTA GRID/LIST
    const viewButtons = document.querySelectorAll('.view-mode-buttons .btn');
    let currentView = localStorage.getItem('shopViewMode') || 'grid';
    
    function applyViewMode(mode) {
        if (!grid) return;
        
        console.log('Aplicando vista:', mode);
        
        const items = grid.querySelectorAll('.oe_product, .o_wsale_grid_item');
        const cards = grid.querySelectorAll('.oe_product_cart');
        
        if (mode === 'list') {
            grid.classList.add('view-mode-list');
            grid.classList.remove('view-mode-grid');
            
            items.forEach(function(item) {
                item.style.cssText = 'width: 100% !important; max-width: 100% !important; flex: none !important; display: block !important; margin-bottom: 0.75rem !important; padding: 0 !important;';
            });
            
            cards.forEach(function(card) {
                card.style.cssText = 'display: flex !important; flex-direction: row !important; align-items: center !important; height: 130px !important; min-height: 130px !important; padding: 0 !important; overflow: hidden !important; border: 1px solid #e0e0e0 !important; border-radius: 8px !important;';
                
                const img = card.querySelector('.oe_product_image');
                if (img) {
                    img.style.cssText = 'width: 130px !important; min-width: 130px !important; max-width: 130px !important; height: 130px !important; flex: 0 0 130px !important; padding: 0.25rem !important; margin: 0 !important; border: none !important; border-right: 1px solid #e0e0e0 !important;';
                }
                
                const info = card.querySelector('.o_wsale_product_information');
                if (info) {
                    info.style.cssText = 'display: flex !important; flex-direction: row !important; align-items: center !important; justify-content: space-between !important; padding: 0 1rem !important; flex: 1 1 auto !important; gap: 1rem !important;';
                }
                
                const title = card.querySelector('.product_title, .o_wsale_products_item_title');
                if (title) {
                    title.style.cssText = 'font-size: 1rem !important; margin: 0 !important; flex: 2 1 auto !important; overflow: hidden !important; text-overflow: ellipsis !important; white-space: nowrap !important;';
                }
                
                const price = card.querySelector('.product_price, .o_wsale_product_price');
                if (price) {
                    price.style.cssText = 'font-size: 1.1rem !important; margin: 0 !important; flex: 0 0 auto !important; white-space: nowrap !important; color: #714B67 !important; font-weight: 700 !important;';
                }
                
                const btnContainer = card.querySelector('.product_action_button');
                if (btnContainer) {
                    btnContainer.style.cssText = 'margin: 0 !important; padding: 0 !important; flex: 0 0 auto !important;';
                    const btn = btnContainer.querySelector('.btn');
                    if (btn) {
                        btn.style.cssText = 'padding: 0.4rem 1rem !important; width: auto !important; font-size: 0.85rem !important; border-radius: 20px !important;';
                    }
                }
                
                // Ocultar badges en lista - más específico
                const badges = card.querySelectorAll('.product_zone_badge, .o_wsale_category_pill, .badge, [class*="badge"]');
                badges.forEach(function(badge) {
                    badge.style.cssText = 'display: none !important;';
                });
            });
            
        } else {
            grid.classList.remove('view-mode-list');
            grid.classList.add('view-mode-grid');
            
            items.forEach(function(item) {
                item.style.cssText = '';
            });
            
            cards.forEach(function(card) {
                card.style.cssText = '';
                
                const img = card.querySelector('.oe_product_image');
                if (img) img.style.cssText = '';
                
                const info = card.querySelector('.o_wsale_product_information');
                if (info) info.style.cssText = '';
                
                const title = card.querySelector('.product_title, .o_wsale_products_item_title');
                if (title) title.style.cssText = '';
                
                const price = card.querySelector('.product_price, .o_wsale_product_price');
                if (price) price.style.cssText = '';
                
                const btnContainer = card.querySelector('.product_action_button');
                if (btnContainer) {
                    btnContainer.style.cssText = '';
                    const btn = btnContainer.querySelector('.btn');
                    if (btn) btn.style.cssText = '';
                }
                
                const badges = card.querySelectorAll('.product_zone_badge, .o_wsale_category_pill, .badge, [class*="badge"]');
                badges.forEach(function(badge) {
                    badge.style.cssText = '';
                });
            });
        }
        
        console.log('Vista aplicada:', mode);
    }
    
    function updateViewButtons(activeMode) {
        viewButtons.forEach(function(btn) {
            const btnMode = btn.getAttribute('data-view-mode');
            if (btnMode === activeMode) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }
    
    applyViewMode(currentView);
    updateViewButtons(currentView);
    
    viewButtons.forEach(function(btn) {
        btn.addEventListener('click', function() {
            const viewMode = this.getAttribute('data-view-mode');
            applyViewMode(viewMode);
            updateViewButtons(viewMode);
            localStorage.setItem('shopViewMode', viewMode);
        });
    });
});
