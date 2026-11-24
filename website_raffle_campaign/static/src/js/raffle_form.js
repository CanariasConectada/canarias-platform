import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const MB = 1024 * 1024;

/**
 * Entry form of the raffle landing page: receipt preview and client-side size
 * check, plus a double-submit guard. The server validates everything again.
 */
export class RaffleForm extends Interaction {
    static selector = ".o_raffle_form";
    dynamicContent = {
        _root: {
            "t-on-submit": this.onSubmit,
            "t-on-invalid.capture": this.onInvalid,
        },
        ".o_raffle_file": {
            "t-on-change": this.onFileChange,
        },
        ".o_raffle_file_clear": {
            "t-on-click": this.onClear,
        },
        _window: {
            // Coming back with the back button must not leave a dead button.
            "t-on-pageshow": this.resetButton,
        },
    };

    setup() {
        this.maxBytes = (parseInt(this.el.dataset.maxMb, 10) || 10) * MB;
        this.fileInput = this.el.querySelector(".o_raffle_file");
        this.preview = this.el.querySelector(".o_raffle_preview");
        this.errorEl = this.el.querySelector(".o_raffle_file_error");
        this.button = this.el.querySelector(".o_raffle_submit");
        this.thumbUrl = null;
    }

    destroy() {
        this.revokeThumb();
    }

    revokeThumb() {
        if (this.thumbUrl) {
            URL.revokeObjectURL(this.thumbUrl);
            this.thumbUrl = null;
        }
    }

    formatSize(bytes) {
        return bytes >= MB
            ? `${(bytes / MB).toFixed(1)} MB`
            : `${Math.max(1, Math.round(bytes / 1024))} KB`;
    }

    onFileChange() {
        this.revokeThumb();
        this.errorEl.textContent = "";
        this.errorEl.classList.add("d-none");
        this.fileInput.setCustomValidity("");
        // Clear a previous "too large" mark even when the selection is now empty.
        this.el.classList.remove("o_raffle_drop_invalid");
        const file = this.fileInput.files[0];
        if (!file) {
            this.preview.classList.add("d-none");
            return;
        }
        if (file.size > this.maxBytes) {
            const message = this.fileInput.dataset.tooBig;
            this.fileInput.setCustomValidity(message);
            this.errorEl.textContent = message;
            this.errorEl.classList.remove("d-none");
            this.preview.classList.add("d-none");
            this.el.classList.add("o_raffle_drop_invalid");
            return;
        }
        this.el.classList.remove("o_raffle_drop_invalid");
        const thumb = this.preview.querySelector(".o_raffle_thumb");
        if (file.type.startsWith("image/") && file.type !== "image/heic") {
            this.thumbUrl = URL.createObjectURL(file);
            thumb.src = this.thumbUrl;
            thumb.classList.remove("d-none");
        } else {
            thumb.removeAttribute("src");
            thumb.classList.add("d-none");
        }
        this.preview.querySelector(".o_raffle_file_name").textContent = file.name;
        this.preview.querySelector(".o_raffle_file_size").textContent = this.formatSize(
            file.size
        );
        this.preview.classList.remove("d-none");
    }

    onClear() {
        this.fileInput.value = "";
        this.onFileChange();
        this.fileInput.focus();
    }

    onSubmit() {
        // ``submit`` only fires once the browser validation has passed.
        this.button.disabled = true;
        this.button.classList.add("o_raffle_submitting");
        this.button.querySelector(".o_raffle_submit_label").classList.add("d-none");
        this.button.querySelector(".o_raffle_submit_busy").classList.remove("d-none");
    }

    onInvalid() {
        this.resetButton();
    }

    resetButton() {
        this.button.disabled = false;
        this.button.classList.remove("o_raffle_submitting");
        this.button.querySelector(".o_raffle_submit_label").classList.remove("d-none");
        this.button.querySelector(".o_raffle_submit_busy").classList.add("d-none");
    }
}

registry.category("public.interactions").add("website_raffle_campaign.raffle_form", RaffleForm);
