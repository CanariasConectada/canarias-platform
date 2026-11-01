import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import {
    ariaFor,
    carouselOptions,
    indicatorLabel,
    indicatorStates,
    keyAction,
    panelsToClose,
    targetIdFromHref,
    triggerKind,
} from "@company_certification/interactions/landing_body_logic";

const TRIGGERS =
    "a[data-bs-toggle], .carousel-control-prev, .carousel-control-next, " +
    ".carousel-indicators a, .modal .btn-close";

/**
 * Drives the Bootstrap widgets inside a certification landing body by hand.
 *
 * The body is a sanitized HTML field: on write, <button>, role, aria-* and
 * every data-bs-* attribute except data-bs-toggle are stripped, so the
 * carousel (autoplay, prev/next arrows, indicators), the close links of the
 * ODS modals and the "one panel open" of an accordion cannot rely on
 * Bootstrap's data API, and the link triggers are neither announced as
 * buttons nor answer Space. The markup that survives is enough to wire them
 * here: <a href="#id" class="carousel-control-prev|next">, the indicator
 * links inside .carousel-indicators (one per slide, in order),
 * <a class="btn-close"> inside a modal and <a data-bs-toggle href="#id">.
 *
 * Every decision lives in landing_body_logic.js, which is tested in node;
 * this class only reads the page and applies the answer.
 */
export class CertificationLandingBody extends Interaction {
    static selector = ".o_cc_landing_richtext";
    dynamicContent = {
        ".carousel-control-prev": { "t-on-click.prevent": this.onPrev },
        ".carousel-control-next": { "t-on-click.prevent": this.onNext },
        ".carousel-indicators a": { "t-on-click.prevent": this.onIndicator },
        ".modal .btn-close": { "t-on-click.prevent": this.onClose },
        ".accordion .collapse": { "t-on-show.bs.collapse": this.onAccordionShow },
        ".collapse": {
            "t-on-shown.bs.collapse": this.onCollapseToggled,
            "t-on-hidden.bs.collapse": this.onCollapseToggled,
        },
        [TRIGGERS]: { "t-on-keydown": this.onTriggerKeydown },
    };

    start() {
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const { ride, interval, rideAttribute } = carouselOptions(reducedMotion);
        for (const el of this.el.querySelectorAll(".carousel")) {
            // website.carousel_slider matches every .carousel too. Without a
            // data-bs-interval (stripped from the body) it marks the carousel
            // data-bs-ride="false" and creates the Bootstrap instance paused;
            // getOrCreateInstance then hands that instance back and ignores
            // the options below, which left the page on its first slide.
            // Whichever interaction starts first, the instance is rebuilt.
            el.dataset.bsRide = rideAttribute;
            window.Carousel.getInstance(el)?.dispose();
            new window.Carousel(el, { ride, interval });
            // Looked up again: the core interaction disposes the same instance.
            this.registerCleanup(() => window.Carousel.getInstance(el)?.dispose());
            // Bootstrap moves the "active" indicator by data-bs-slide-to,
            // which the sanitizer removed: follow the slide by position.
            this.addListener(el, "slid.bs.carousel", (ev) => {
                this.markActiveIndicator(el, ev.to);
            });
        }
        for (const triggerEl of this.el.querySelectorAll(TRIGGERS)) {
            this.describeTrigger(triggerEl);
        }
    }

    kindOf(triggerEl) {
        return triggerKind({
            classes: [...triggerEl.classList],
            toggle: triggerEl.dataset.bsToggle,
            inIndicators: Boolean(triggerEl.closest(".carousel-indicators")),
        });
    }

    /** Put back the role and ARIA the sanitizer removed from a trigger. */
    describeTrigger(triggerEl) {
        const kind = this.kindOf(triggerEl);
        const targetId = targetIdFromHref(triggerEl.getAttribute("href"));
        const targetEl = targetId && this.el.querySelector(`#${CSS.escape(targetId)}`);
        let label = null;
        if (kind === "indicator") {
            const links = [...triggerEl.parentElement.querySelectorAll("a")];
            const index = links.indexOf(triggerEl);
            const slideEl = triggerEl
                .closest(".carousel")
                .querySelectorAll(".carousel-item")[index];
            label = indicatorLabel(slideEl?.querySelector("h1,h2,h3,h4,h5,h6")?.textContent, index);
        }
        const attrs = ariaFor(kind, {
            targetId,
            expanded: Boolean(targetEl?.classList.contains("show")),
            hasHref: triggerEl.hasAttribute("href"),
            label,
        });
        for (const [name, value] of Object.entries(attrs)) {
            triggerEl.setAttribute(name, value);
        }
    }

    carouselOf(ev) {
        const el = ev.currentTarget.closest(".carousel");
        return el ? window.Carousel.getOrCreateInstance(el) : null;
    }

    onPrev(ev) {
        this.carouselOf(ev)?.prev();
    }

    onNext(ev) {
        this.carouselOf(ev)?.next();
    }

    onIndicator(ev) {
        const links = [...ev.currentTarget.parentElement.querySelectorAll("a")];
        this.carouselOf(ev)?.to(links.indexOf(ev.currentTarget));
    }

    markActiveIndicator(carouselEl, index) {
        const links = carouselEl.querySelectorAll(".carousel-indicators a");
        indicatorStates(links.length, index).forEach((active, position) => {
            links[position].classList.toggle("active", active);
            links[position].setAttribute("aria-current", active ? "true" : "false");
        });
    }

    onAccordionShow(ev) {
        const accordionEl = ev.target.closest(".accordion");
        const panels = [...accordionEl.querySelectorAll(".collapse")].map((el) => ({
            id: el.id,
            shown: el.classList.contains("show"),
        }));
        for (const id of panelsToClose(panels, ev.target.id)) {
            const openEl = accordionEl.querySelector(`#${CSS.escape(id)}`);
            window.Collapse.getOrCreateInstance(openEl, { toggle: false }).hide();
        }
    }

    /** Keep aria-expanded of every trigger of a panel in step with it. */
    onCollapseToggled(ev) {
        for (const triggerEl of this.el.querySelectorAll('a[data-bs-toggle="collapse"]')) {
            if (targetIdFromHref(triggerEl.getAttribute("href")) === ev.target.id) {
                this.describeTrigger(triggerEl);
            }
        }
    }

    onTriggerKeydown(ev) {
        const action = keyAction(ev.key, {
            hasHref: ev.currentTarget.hasAttribute("href"),
            modified: ev.ctrlKey || ev.metaKey || ev.altKey,
        });
        if (action === "activate") {
            // Space on a link scrolls the page: stop that, then act like a
            // button would.
            ev.preventDefault();
            ev.currentTarget.click();
        }
    }

    onClose(ev) {
        const modalEl = ev.currentTarget.closest(".modal");
        if (modalEl) {
            window.Modal.getOrCreateInstance(modalEl).hide();
        }
    }
}

registry
    .category("public.interactions")
    .add("company_certification.landing_body", CertificationLandingBody);
