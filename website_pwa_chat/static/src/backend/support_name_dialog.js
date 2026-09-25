/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {Component, useState} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";

/**
 * "Who is asking?" -- shown to a walk-in community guest before their
 * support conversation opens. Their account is named "Invitado 3f9a2c",
 * which tells the agent nothing; the website asks the same question on its
 * identify card, and the answer lands in the same place.
 *
 * The server validates again: this only saves a round trip for an empty
 * name.
 */
export class SupportNameDialog extends Component {
    static template = "website_pwa_chat.SupportNameDialog";
    static components = {Dialog};
    static props = {
        close: Function,
        onConfirm: Function,
    };

    setup() {
        this.state = useState({name: "", email: "", missing: false, busy: false});
    }

    async confirm() {
        const name = this.state.name.trim();
        if (!name) {
            this.state.missing = true;
            return;
        }
        this.state.busy = true;
        try {
            await this.props.onConfirm({name, email: this.state.email.trim()});
            this.props.close();
        } finally {
            this.state.busy = false;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.confirm();
        }
    }
}
