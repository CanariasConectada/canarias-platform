// MICROSITE COMPANY SWITCH - Cookie Manager
(function() {
    'use strict';
    
    function getCookie(name) {
        var value = '; ' + document.cookie;
        var parts = value.split('; ' + name + '=');
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }
    
    function setCookie(name, value, days) {
        var expires = '';
        if (days) {
            var date = new Date();
            date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
            expires = '; expires=' + date.toUTCString();
        }
        document.cookie = name + '=' + value + expires + '; path=/; SameSite=Lax';
    }
    
    // SOLO crear cookie inicial si no existe
    // La recarga automática se desactivó porque causaba problemas al editar usuarios
    function createInitialCookie() {
        if (!window.odoo || !window.odoo.__session_info__) {
            return false;
        }
        
        var sessionInfo = window.odoo.__session_info__;
        if (!sessionInfo.user_companies) {
            return false;
        }
        
        var existingCookie = getCookie('cids');
        if (existingCookie) {
            return true;
        }
        
        var currentCompany = sessionInfo.user_companies.current_company;
        var allowedCompanies = sessionInfo.user_companies.allowed_companies;
        
        if (!currentCompany || !allowedCompanies) {
            return true;
        }
        
        var allIds = Object.keys(allowedCompanies).map(Number);
        var orderedIds = [currentCompany].concat(allIds.filter(function(id) { 
            return id !== currentCompany; 
        }));
        var cidsValue = orderedIds.join('-');
        
        setCookie('cids', cidsValue, 90);
        console.log('[MCS] Cookie inicial creada:', cidsValue);
        return true;
    }
    
    // Crear cookie inicial si no existe
    var attempts = 0;
    var interval = setInterval(function() {
        attempts++;
        if (createInitialCookie() || attempts > 50) {
            clearInterval(interval);
        }
    }, 100);
    
    // NOTA: La recarga automática se eliminó porque causaba redirecciones
    // al intentar editar usuarios en Ajustes > Usuarios
    // El cambio de compañía ahora requiere recarga manual o usar el switcher
    
})();
