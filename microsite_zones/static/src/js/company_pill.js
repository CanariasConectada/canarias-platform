/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.CompanyPill = publicWidget.Widget.extend({
    selector: '.oe_product_cart',
    
    async start() {
        this._super.apply(this, arguments);
        await this._updateCompanyPill();
    },
    
    async _updateCompanyPill() {
        const form = this.el;
        const companyId = form.dataset.companyId;
        
        if (!companyId) return;
        
        const pill = form.querySelector('.o_wsale_company_pill span');
        if (!pill) return;
        
        try {
            // Llamar al endpoint para obtener el nombre de la compañía
            const result = await rpc('/microsite_zones/company_name', {
                company_id: parseInt(companyId)
            });
            
            if (result && result.name) {
                const icon = pill.querySelector('i');
                pill.textContent = ' ' + result.name;
                if (icon) {
                    pill.prepend(icon);
                }
            }
        } catch (error) {
            console.log('Error al obtener nombre de compañía:', error);
        }
    }
});
