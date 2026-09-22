/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";
import {listView} from "@web/views/list/list_view";
import {ListController} from "@web/views/list/list_controller";

/**
 * "My shops": a click on a row opens the page content of that shop.
 *
 * The list is the merchant's own sites with three buttons per row
 * (Content / Pages / Orders). Opening the row used to land on the website
 * form, which a merchant cannot edit and was not asking for (reported
 * 2026-09-15). A row now behaves as its Content button: the same server
 * method, so the ownership guard stays on the server, and the same action
 * comes back. When the method answers nothing, the row opens as before.
 */
export class MerchantWebsiteListController extends ListController {
    async openRecord(record, options) {
        // Through the button path, not a bare ORM call: `call_button` runs
        // the returned action through the server's clean_action (views
        // derived from view_mode), which a raw orm.call skips and doAction
        // then fails on "action.views is undefined" (2026-09-16).
        return this.actionService.doActionButton({
            type: "object",
            name: "action_microsite_content",
            resModel: record.resModel,
            resId: record.resId,
            resIds: [record.resId],
            context: record.context,
            onClose: () => this.model.load(),
        });
    }
}

export const merchantWebsiteListView = {
    ...listView,
    Controller: MerchantWebsiteListController,
};

registry.category("views").add("merchant_website_list", merchantWebsiteListView);
