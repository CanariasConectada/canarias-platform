/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebsiteSwitcherSystrayItem } from "@website/client_actions/website_preview/website_switcher_systray_item";

patch(WebsiteSwitcherSystrayItem.prototype, {
    getElements() {
        const elements = super.getElements(...arguments);
        // Sobrescribir el callback de cada elemento para evitar redirección
        elements.forEach(el => {
            const originalCallback = el.callback;
            el.callback = () => {
                // Forzar bypass de redirección de dominio
                const session = odoo.__session_info__;
                if (session) {
                    session.website_bypass_domain_redirect = true;
                }
                // Llamar al callback original
                originalCallback();
            };
        });
        return elements;
    }
});
