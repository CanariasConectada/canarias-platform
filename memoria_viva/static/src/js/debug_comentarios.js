/*
 * Script de diagnóstico para consola F12
 * Copia y pega todo este código en la consola del navegador (F12 → Console)
 */

console.log('=== DIAGNÓSTICO DE COMENTARIOS ===');

// 1. Verificar si existe el elemento lugar_id
var lugarIdInput = document.getElementById('lugar_id') || document.querySelector('input[name="lugar_id"]');
console.log('1. Input lugar_id encontrado:', lugarIdInput ? '✅ SÍ' : '❌ NO');
if (lugarIdInput) {
    console.log('   Valor:', lugarIdInput.value);
    console.log('   ID:', lugarIdInput.id);
    console.log('   Name:', lugarIdInput.name);
}

// 2. Verificar si existe el contenedor de comentarios
var lista = document.getElementById('comentarios-lista');
console.log('2. Contenedor comentarios-lista:', lista ? '✅ SÍ' : '❌ NO');

// 3. Verificar configuración de comentarios (elemento en el DOM)
var configEl = document.getElementById('mv-config');
console.log('3. Elemento de configuración:', configEl ? '✅ SÍ' : '❌ NO (no crítico)');

// 4. Probar llamada AJAX manualmente
console.log('4. Probando llamada AJAX...');
if (lugarIdInput && lugarIdInput.value) {
    var lugarId = lugarIdInput.value;
    var url = '/memoria-viva/comentario/listar?lugar_id=' + lugarId + '&offset=0&limit=10';
    
    console.log('   URL:', url);
    
    fetch(url, {
        method: 'GET',
        headers: {
            'Accept': 'application/json'
        },
        credentials: 'same-origin'
    })
    .then(function(response) {
        console.log('   Status HTTP:', response.status);
        if (!response.ok) {
            throw new Error('HTTP ' + response.status);
        }
        return response.json();
    })
    .then(function(data) {
        console.log('   Respuesta:', data);
        if (data.success) {
            console.log('   ✅ ÉXITO - Comentarios recibidos:', data.total);
            if (data.comentarios && data.comentarios.length > 0) {
                console.log('   Primer comentario:', data.comentarios[0].contenido);
            } else {
                console.log('   ⚠️ No hay comentarios en la respuesta');
            }
        } else {
            console.log('   ❌ Error en respuesta:', data.error);
        }
    })
    .catch(function(err) {
        console.log('   ❌ Error en fetch:', err.message);
    });
} else {
    console.log('   ❌ No se pudo obtener lugar_id');
}

// 5. Verificar si hay errores previos en la consola
console.log('5. Verifica arriba si hay errores (en rojo) en la consola');

// 6. Información del usuario
console.log('6. Información de sesión:');
console.log('   URL actual:', window.location.href);
console.log('   User Agent:', navigator.userAgent.substring(0, 50) + '...');

console.log('=== FIN DEL DIAGNÓSTICO ===');
