/**
 * Microsite Complete - JS Only Solution
 */

(function() {
    'use strict';
    
    function isMicrosite() {
        if (document.body.classList.contains('o_zone_website') || 
            document.body.classList.contains('o_canarias_website')) {
            return false;
        }
        var zoneIdMeta = document.querySelector('meta[name="website-zone-id"]');
        if (zoneIdMeta && zoneIdMeta.content && zoneIdMeta.content.trim() !== '') {
            return false;
        }
        return true;
    }
    
    function transformMicrosites() {
        if (!isMicrosite()) return;
        
        document.querySelectorAll('.oe_product_cart').forEach(function(card) {
            if (card.dataset.micrositeTransformed === 'true') return;
            card.dataset.micrositeTransformed = 'true';
            
            var infoDiv = card.querySelector('.o_wsale_product_information');
            var titleLink = card.querySelector('.product_title a, h3 a');
            
            // 1. STYLE MAIN PRICE - Purple color, only if > 0
            var mainPrice = card.querySelector('.o_wsale_product_info_attributes_wrapper .product_price, .o_wsale_product_information_text .product_price');
            if (mainPrice) {
                var priceText = mainPrice.textContent.trim().replace(/[^\d,\.]/g, '').replace(',', '.');
                var priceValue = parseFloat(priceText) || 0;
                
                if (priceValue > 0) {
                    mainPrice.style.cssText = 'color: #714B67 !important; font-weight: 600 !important; font-size: 1.1rem !important; margin-bottom: 8px !important;';
                    mainPrice.querySelectorAll('*').forEach(function(el) {
                        el.style.color = '#714B67';
                    });
                } else {
                    mainPrice.style.display = 'none';
                }
            }
            
            // 2. HIDE SECOND PRICE
            var subPrice = card.querySelector('.o_wsale_product_sub .product_price');
            if (subPrice) {
                subPrice.style.display = 'none';
            }
            
            // 3. ADD COMPANY BADGE
            if (!card.querySelector('.microsite-company-badge')) {
                var companyName = 'Tienda';
                if (titleLink) {
                    var href = titleLink.getAttribute('href') || '';
                    var domainMatch = href.match(/https?:\/\/([^\.]+)\./);
                    if (domainMatch) {
                        companyName = domainMatch[1].toUpperCase();
                    }
                }
                
                var badge = document.createElement('div');
                badge.className = 'microsite-company-badge';
                badge.style.cssText = 'background: #f8f9fa; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; color: #666; margin-bottom: 8px; display: inline-block; text-transform: uppercase;';
                badge.textContent = companyName;
                if (infoDiv) {
                    infoDiv.insertBefore(badge, infoDiv.firstChild);
                }
            }
            
            // 4. HIDE "VER EN TIENDA" BUTTON
            var allBtns = card.querySelectorAll('.btn, .btn-primary');
            allBtns.forEach(function(btn) {
                var text = btn.textContent.toLowerCase();
                if (text.includes('tienda') || text.includes('ver en')) {
                    btn.style.display = 'none';
                }
            });
            
            // 5. ADD CART BUTTON
            if (!card.querySelector('.microsite-add-cart-btn')) {
                var btnContainer = card.querySelector('.product_action_button') || 
                                   card.querySelector('.o_wsale_product_btn');
                
                if (btnContainer) {
                    var cartBtn = document.createElement('button');
                    cartBtn.className = 'btn btn-primary w-100 microsite-add-cart-btn';
                    cartBtn.style.cssText = 'background-color: #714B67; border-color: #714B67;';
                    cartBtn.innerHTML = '<i class="fa fa-shopping-cart me-2"></i><span>Añadir al carrito</span>';
                    cartBtn.type = 'button';
                    
                    cartBtn.addEventListener('click', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        
                        var productLink = card.querySelector('a[href*="/shop/"]');
                        if (productLink) {
                            var href = productLink.getAttribute('href');
                            var match = href.match(/product\/([^-]+)/) || href.match(/\/shop\/([^?/]+)/);
                            if (match) {
                                addToCart(match[1], cartBtn);
                            }
                        }
                    });
                    
                    btnContainer.innerHTML = '';
                    btnContainer.appendChild(cartBtn);
                }
            }
        });
    }
    
    function addToCart(productId, btn) {
        var csrf = document.querySelector('input[name="csrf_token"]');
        var formData = new FormData();
        formData.append('product_id', productId);
        formData.append('add_qty', 1);
        formData.append('csrf_token', csrf ? csrf.value : '');
        
        var original = btn.innerHTML;
        btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i>';
        btn.disabled = true;
        
        fetch('/shop/cart/update_json', {
            method: 'POST',
            body: formData,
            headers: {'X-Requested-With': 'XMLHttpRequest'}
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.cart_quantity !== undefined) {
                document.querySelectorAll('.o_wsale_my_cart .badge, .my_cart_quantity').forEach(function(b) {
                    b.textContent = data.cart_quantity;
                    b.style.display = data.cart_quantity > 0 ? 'inline-block' : 'none';
                });
                
                btn.innerHTML = '<i class="fa fa-check me-2"></i><span>Añadido</span>';
                btn.style.backgroundColor = '#28a745';
                btn.style.borderColor = '#28a745';
                
                setTimeout(function() {
                    btn.innerHTML = original;
                    btn.style.backgroundColor = '';
                    btn.style.borderColor = '';
                    btn.disabled = false;
                }, 1500);
            }
        })
        .catch(function() {
            btn.innerHTML = '<i class="fa fa-times me-2"></i><span>Error</span>';
            btn.style.backgroundColor = '#dc3545';
            setTimeout(function() {
                btn.innerHTML = original;
                btn.style.backgroundColor = '';
                btn.disabled = false;
            }, 1500);
        });
    }
    
    function observe() {
        var observer = new MutationObserver(function(mutations) {
            var run = false;
            mutations.forEach(function(m) {
                m.addedNodes.forEach(function(n) {
                    if (n.nodeType === 1 && (n.classList.contains('oe_product') || n.classList.contains('oe_product_cart'))) {
                        run = true;
                    }
                });
            });
            if (run) setTimeout(transformMicrosites, 100);
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            transformMicrosites();
            observe();
        });
    } else {
        transformMicrosites();
        observe();
    }
    
    window.addEventListener('popstate', function() {
        document.querySelectorAll('.oe_product_cart').forEach(function(c) {
            c.dataset.micrositeTransformed = '';
        });
        setTimeout(transformMicrosites, 300);
    });
})();
