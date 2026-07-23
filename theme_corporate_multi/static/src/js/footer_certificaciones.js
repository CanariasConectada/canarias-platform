// Mostrar enlaces de certificaciones en el footer
// Este script es un respaldo - el principal está inline en layout.xml
(function() {
    'use strict';

    function detectarCertificaciones() {
        var container = document.getElementById('footer-certificaciones-container');
        if (!container) return false;
        if (container.getAttribute('data-procesado') === 'true') return true;

        var imgs = document.querySelectorAll('img');
        var tieneSilver = false;
        var tieneSostenible = false;

        for (var i = 0; i < imgs.length; i++) {
            var img = imgs[i];
            var src = (img.getAttribute('src') || '').toLowerCase();
            var alt = (img.getAttribute('alt') || '').toLowerCase();
            var dataSrc = (img.getAttribute('data-src') || '').toLowerCase();

            if (src.indexOf('sello_silver') > -1 ||
                alt.indexOf('silver') > -1 ||
                dataSrc.indexOf('sello_silver') > -1) {
                tieneSilver = true;
            }
            if (src.indexOf('sello_sostenible') > -1 ||
                alt.indexOf('sostenible') > -1 ||
                dataSrc.indexOf('sello_sostenible') > -1) {
                tieneSostenible = true;
            }
        }

        if (!tieneSilver && !tieneSostenible) return false;

        var html = '';
        if (tieneSilver) {
            html += '<a href="https://canariasconectada.es/silver-economy" target="_blank" style="display:inline-block;background:rgba(192,192,192,0.2);border:1px solid #C0C0C0;color:#C0C0C0;padding:0.25rem 0.75rem;border-radius:0.25rem;text-decoration:none;margin:0.15rem;font-size:0.8rem;"><i class="fa fa-leaf"></i> Comercio Silver Economy</a>';
        }
        if (tieneSostenible) {
            html += '<a href="https://canariasconectada.es/sostenible" target="_blank" style="display:inline-block;background:rgba(40,167,69,0.2);border:1px solid #28a745;color:#28a745;padding:0.25rem 0.75rem;border-radius:0.25rem;text-decoration:none;margin:0.15rem;font-size:0.8rem;"><i class="fa fa-recycle"></i> Comercio Sostenible</a>';
        }

        container.innerHTML = html;
        container.setAttribute('data-procesado', 'true');
        return true;
    }

    function intentarEjecutar() {
        if (detectarCertificaciones()) return;
        setTimeout(intentarEjecutar, 200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', intentarEjecutar);
    } else {
        intentarEjecutar();
    }

    setTimeout(detectarCertificaciones, 500);
    setTimeout(detectarCertificaciones, 1000);
    setTimeout(detectarCertificaciones, 2000);
})();
