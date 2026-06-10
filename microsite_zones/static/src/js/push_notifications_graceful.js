/** @odoo-module **/

/**
 * Parche para manejar gracefulmente los errores de notificaciones push
 * en microsites donde el push service no está disponible.
 * 
 * Este parche evita que aparezca una notificación sticky de tipo "danger"
 * cuando el servicio de push no está disponible (común en subdominios o
 * ciertos navegadores).
 */

import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(WebClient.prototype, {
    /**
     * Sobrescribe _subscribePush para manejar gracefulmente errores de push
     * no disponible sin mostrar notificaciones intrusivas.
     */
    async _subscribePush(numberTry = 1) {
        // Primero verificar si push está disponible antes de intentar
        const pushManager = await this.pushManager();
        if (!pushManager) {
            // Push manager no disponible, salir silenciosamente
            return;
        }

        // Verificar el estado de permisos antes de suscribir
        try {
            const permissionState = await pushManager.permissionState({
                userVisibleOnly: true,
            });
            if (permissionState === "denied") {
                // Permiso denegado, no intentar suscribir
                return;
            }
        } catch (e) {
            // Si no podemos verificar el estado, continuar de todos modos
            // pero capturaremos errores más adelante
        }

        // Llamar al método original con manejo de errores mejorado
        try {
            await this._super(numberTry);
        } catch (error) {
            // Verificar si es un error de "push service not available"
            const errorMessage = error?.message?.toLowerCase() || "";
            const isPushUnavailableError = 
                errorMessage.includes("push service not available") ||
                errorMessage.includes("registration failed") ||
                errorMessage.includes("not supported") ||
                errorMessage.includes("permission denied") ||
                error.message?.includes("AbortError") ||
                error.message?.includes("NotAllowedError");

            if (isPushUnavailableError) {
                // Error de push no disponible: log silencioso, no notificación
                console.warn("[Push Notifications] Servicio no disponible en este contexto:", error.message);
                return;
            }

            // Para otros errores, usar el comportamiento original pero menos intrusivo
            console.warn("[Push Notifications] Error al suscribir:", error);
            
            // Solo mostrar notificación para errores que no sean de disponibilidad
            // y usar tipo "warning" en lugar de "danger", sin sticky
            this.notification.add(
                _t("Las notificaciones push no están disponibles en este navegador."),
                {
                    title: _t("Notificaciones push"),
                    type: "warning",
                    sticky: false,
                }
            );
        }
    },
});
