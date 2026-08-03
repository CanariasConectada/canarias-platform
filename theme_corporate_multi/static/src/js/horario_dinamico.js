/**
 * Horario Dinámico - Muestra día actual y estado (Abierto/Cerrado)
 * Interpreta horarios tipo "09:00-15:00" o "09:15-13:00 / 16:30-20:00"
 */
(function() {
    'use strict';

    // Array de días en español (getDay: 0=Domingo, 1=Lunes, ...)
    var diasSemana = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];

    // Función para convertir hora "HH:MM" a minutos desde medianoche
    function horaAMinutos(hora) {
        var partes = hora.split(':');
        return parseInt(partes[0]) * 60 + parseInt(partes[1]);
    }

    // Función para verificar si está abierto ahora
    function estaAbierto(horarioTexto) {
        var ahora = new Date();
        var minutosActual = ahora.getHours() * 60 + ahora.getMinutes();

        // Buscar todos los rangos de tiempo (ej. "09:00-15:00" o "09:15-13:00 / 16:30-20:00")
        var rangos = horarioTexto.match(/\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}/g);

        if (!rangos) return null; // No se encontraron horarios

        // Verificar si está dentro de algún rango
        for (var i = 0; i < rangos.length; i++) {
            var partes = rangos[i].split('-');
            var inicio = horaAMinutos(partes[0].trim());
            var fin = horaAMinutos(partes[1].trim());

            if (minutosActual >= inicio && minutosActual <= fin) {
                return true; // Está dentro del horario
            }
        }

        return false; // No está dentro de ningún horario
    }

    // Función para obtener solo el horario (quitar "Cerrado" o "Abierto")
    function extraerHorario(texto) {
        // Buscar patrones de horario
        var match = texto.match(/(\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}.*)/);
        if (match) {
            return match[1].trim();
        }
        return texto;
    }

    function actualizarHorario() {
        var hoy = diasSemana[new Date().getDay()];
        var horaActual = new Date().getHours() + ':' + String(new Date().getMinutes()).padStart(2, '0');

        // Buscar todos los acordeones de horario
        document.querySelectorAll('[id^="horarioCardAccordion"]').forEach(function(acordeon) {
            var button = acordeon.querySelector('.accordion-button');
            if (!button) return;

            var spanPrincipal = button.querySelector('span:first-child');
            var spanHorario = button.querySelector('span.ms-auto, span:last-child');

            if (!spanPrincipal) return;

            var textoCompleto = spanPrincipal.textContent;

            // Verificar si contiene un día de la semana
            var regexDias = /(Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)/i;
            if (!regexDias.test(textoCompleto)) return;

            // Extraer el horario del texto
            var horarioTexto = '';
            if (spanHorario) {
                horarioTexto = spanHorario.textContent;
            } else {
                // Intentar extraer del texto principal
                horarioTexto = extraerHorario(textoCompleto);
            }

            // Determinar si está abierto o cerrado
            var abierto = estaAbierto(horarioTexto);
            var estado = abierto ? 'Abierto' : 'Cerrado';

            // Actualizar el texto del día
            var nuevoTexto = hoy + ': ' + estado;
            spanPrincipal.textContent = nuevoTexto;

            // Cambiar color según estado
            if (abierto) {
                spanPrincipal.style.color = '#28a745'; // Verde para abierto
            } else {
                spanPrincipal.style.color = '#dc3545'; // Rojo para cerrado
            }

            // Actualizar el span de horario si existe
            if (spanHorario && horarioTexto && horarioTexto !== 'Cerrado') {
                spanHorario.textContent = horarioTexto;
            }
        });

        // Actualizar también el horario semanal (resaltar el día actual)
        document.querySelectorAll('.horario-semana-item').forEach(function(item) {
            var spanDia = item.querySelector('span:first-child');
            if (!spanDia) return;

            var diaAbrev = spanDia.textContent.trim();
            var diaActualAbrev = hoy.substring(0, 3);
            if (hoy === 'Miércoles') diaActualAbrev = 'Mié';
            if (hoy === 'Sábado') diaActualAbrev = 'Sáb';
            if (hoy === 'Domingo') diaActualAbrev = 'Dom';

            // Resaltar el día actual
            if (diaAbrev === diaActualAbrev) {
                spanDia.style.fontWeight = '600';
                spanDia.style.color = '#212529';
            }
        });
    }

    // Ejecutar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', actualizarHorario);
    } else {
        actualizarHorario();
    }

    // Múltiples ejecuciones para asegurar
    setTimeout(actualizarHorario, 100);
    setTimeout(actualizarHorario, 500);
    setTimeout(actualizarHorario, 1000);

    // Actualizar cada hora para mantener el estado actualizado sin saturar
    setInterval(actualizarHorario, 3600000);
})();
