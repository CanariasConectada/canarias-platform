/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";

/**
 * Debug de Aislamiento de Compañías - Frontend
 * 
 * Este módulo proporciona logs en consola para verificar el funcionamiento
 * del aislamiento estricto de compañías.
 */

// Colores para los logs
const LOG_STYLES = {
    info: 'color: #2196F3; font-weight: bold;',
    success: 'color: #4CAF50; font-weight: bold;',
    warning: 'color: #FF9800; font-weight: bold;',
    error: 'color: #f44336; font-weight: bold;',
    header: 'color: #9C27B0; font-size: 14px; font-weight: bold;',
    data: 'color: #666;'
};

/**
 * Log formateado con estilos
 */
function logStyled(message, style = 'info', data = null) {
    const prefix = '%c[MCS-ISOLATION]';
    console.log(prefix, LOG_STYLES[style], message);
    if (data) {
        console.log('%c  Datos:', LOG_STYLES.data, data);
    }
}

/**
 * Imprime un header visual
 */
function logHeader(title) {
    console.log('\n');
    console.log('%c' + '='.repeat(60), LOG_STYLES.header);
    console.log('%c' + title, LOG_STYLES.header);
    console.log('%c' + '='.repeat(60), LOG_STYLES.header);
}

/**
 * Verifica y loguea información de la cookie cids
 */
function checkCidsCookie() {
    const cids = document.cookie
        .split('; ')
        .find(row => row.startsWith('cids='));
    
    if (cids) {
        const value = cids.split('=')[1];
        logStyled('Cookie cids encontrada:', 'success', value);
        return value;
    } else {
        logStyled('Cookie cids NO encontrada', 'warning');
        return null;
    }
}

/**
 * Verifica y loguea información del session_info
 */
function checkSessionInfo() {
    if (session && session.user_companies) {
        logStyled('Session Info - User Companies:', 'info', {
            current_company: session.user_companies.current_company,
            allowed_companies: session.user_companies.allowed_companies,
        });
        return session.user_companies;
    } else {
        logStyled('Session Info NO disponible', 'warning');
        return null;
    }
}

/**
 * Compara cookie vs session para detectar inconsistencias
 */
function checkConsistency() {
    logHeader('VERIFICACIÓN DE CONSISTENCIA');
    
    const cookieCids = checkCidsCookie();
    const sessionInfo = checkSessionInfo();
    
    if (cookieCids && sessionInfo) {
        const cookieCompanyId = parseInt(cookieCids.split('-')[0]);
        const sessionCompanyId = sessionInfo.current_company?.id;
        
        if (cookieCompanyId === sessionCompanyId) {
            logStyled(
                `✅ CONSISTENTE: Cookie (${cookieCompanyId}) = Session (${sessionCompanyId})`,
                'success'
            );
        } else {
            logStyled(
                `❌ INCONSISTENTE: Cookie (${cookieCompanyId}) ≠ Session (${sessionCompanyId})`,
                'error'
            );
        }
        
        // Verificar aislamiento
        const allowedCount = sessionInfo.allowed_companies?.length || 0;
        if (allowedCount === 1) {
            logStyled(
                `✅ AISLAMIENTO CORRECTO: Solo 1 compañía permitida`,
                'success',
                sessionInfo.allowed_companies
            );
        } else {
            logStyled(
                `⚠️ AISLAMIENTO DÉBIL: ${allowedCount} compañías permitidas`,
                'warning',
                sessionInfo.allowed_companies
            );
        }
    }
}

/**
 * Realiza llamada RPC al backend para obtener info de debug
 */
async function fetchBackendDebug() {
    logHeader('INFO DEL BACKEND');
    
    try {
        logStyled('Consultando backend...', 'info');
        
        const result = await rpc('/microsite_company_switch/debug/isolation', {});
        
        if (result.status === 'success') {
            logStyled('Datos del usuario:', 'info', result.user);
            logStyled('Contexto actual:', 'info', result.context);
            logStyled('Estado de aislamiento:', 'info', result.isolation_status);
            logStyled('Contactos visibles:', 'info', {
                total: result.partners.total_visible,
                sample: result.partners.sample
            });
            
            // Verificar consistencia frontend vs backend
            const cookieCids = checkCidsCookie();
            if (cookieCids) {
                const cookieCompanyId = parseInt(cookieCids.split('-')[0]);
                const backendCompanyId = result.context.company_id;
                
                if (cookieCompanyId === backendCompanyId) {
                    logStyled(
                        `✅ FRONTEND-BACKEND SINCRONIZADOS: ${cookieCompanyId}`,
                        'success'
                    );
                } else {
                    logStyled(
                        `❌ DESFASE FRONTEND-BACKEND: Cookie=${cookieCompanyId}, Backend=${backendCompanyId}`,
                        'error'
                    );
                }
            }
            
            return result;
        } else {
            logStyled('Error en respuesta del backend:', 'error', result.message);
        }
    } catch (error) {
        logStyled('Error llamando al backend:', 'error', error.message);
    }
}

/**
 * Obtiene información de las reglas de seguridad
 */
async function fetchRulesDebug() {
    logHeader('REGLAS DE SEGURIDAD');
    
    try {
        const result = await rpc('/microsite_company_switch/debug/rules', {});
        
        if (result.status === 'success') {
            result.rules.forEach(rule => {
                const status = rule.active ? '✅ ACTIVA' : '❌ INACTIVA';
                const style = rule.active ? 'success' : 'error';
                logStyled(
                    `[${rule.id}] ${rule.name} ${status}`,
                    style,
                    {
                        dominio: rule.domain,
                        grupos: rule.groups
                    }
                );
            });
        } else {
            logStyled('Error:', 'error', result.message);
        }
    } catch (error) {
        logStyled('Error:', 'error', error.message);
    }
}

/**
 * Ejecuta todos los tests de aislamiento
 */
async function runAllTests() {
    logHeader('TEST COMPLETO DE AISLAMIENTO');
    
    // Test 1: Consistencia
    checkConsistency();
    
    // Test 2: Backend
    await fetchBackendDebug();
    
    // Test 3: Reglas
    await fetchRulesDebug();
    
    logHeader('TEST COMPLETADO');
}

/**
 * Inicializa el debug cuando el documento está listo
 */
function initDebug() {
    // Log inicial
    logHeader('MICROSITE COMPANY SWITCH - DEBUG INICIALIZADO');
    
    // Exponer funciones globalmente para uso en consola
    window.MCSDebug = {
        checkCookie: checkCidsCookie,
        checkSession: checkSessionInfo,
        checkConsistency: checkConsistency,
        fetchBackend: fetchBackendDebug,
        fetchRules: fetchRulesDebug,
        runAll: runAllTests,
        help: () => {
            console.log('%c[MCS-ISOLATION] Comandos disponibles:', LOG_STYLES.header);
            console.log('  MCSDebug.checkCookie()    - Ver cookie cids');
            console.log('  MCSDebug.checkSession()   - Ver session_info');
            console.log('  MCSDebug.checkConsistency() - Verificar consistencia');
            console.log('  MCSDebug.fetchBackend()   - Obtener info del backend');
            console.log('  MCSDebug.fetchRules()     - Ver reglas de seguridad');
            console.log('  MCSDebug.runAll()         - Ejecutar todos los tests');
        }
    };
    
    logStyled('Funciones disponibles en window.MCSDebug', 'info');
    logStyled('Escribe MCSDebug.help() para ver comandos', 'info');
    
    // Verificación inicial
    checkConsistency();
    
    // Ejecutar test completo después de un momento
    setTimeout(() => {
        fetchBackendDebug();
    }, 2000);
}

// Inicializar cuando el DOM esté listo
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDebug);
} else {
    initDebug();
}

// También registrar en el registry de Odoo para asegurar carga
registry.category("web.client_actions").add("microsite_company_switch.isolation_debug", {
    init: initDebug,
});

export default {
    checkConsistency,
    fetchBackendDebug,
    fetchRulesDebug,
    runAllTests,
};
