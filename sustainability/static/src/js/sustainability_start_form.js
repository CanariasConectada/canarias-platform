/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";

patch(ListController.prototype, {
    async createRecord() {
        // Si es la vista list de survey.user_input con contexto Silver Economy,
        // abrir la encuesta directamente en nueva pestaña sin mostrar formulario vacío.
        if (
            this.props.resModel === "survey.user_input" &&
            this.props.context?.is_sustainability
        ) {
            window.open("/sostenibilidad/start", "_blank");
            return;
        }
        await super.createRecord(...arguments);
    }
});
