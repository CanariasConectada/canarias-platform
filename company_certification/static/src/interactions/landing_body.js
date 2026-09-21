import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

/**
 * Drives the Bootstrap widgets inside a certification landing body by hand.
 *
 * The body is a sanitized HTML field: on write, <button> and every
 * data-bs-* attribute except data-bs-toggle are stripped, so the carousel
 * (autoplay, prev/next arrows, indicators) and the close links of the ODS
 * modals cannot rely on Bootstrap's data API. The markup that survives is
 * enough to wire them here: <a href="#id" class="carousel-control-prev|next">,
 * the indicator links inside .carousel-indicators (one per slide, in order)
 * and <a class="btn-close"> inside a modal. The modals themselves still open
 * through data-bs-toggle="modal" + href, which Bootstrap resolves natively,
 * and so do the collapses; data-bs-parent is stripped, so the "one panel open
 * at a time" of an accordion is restored here.
 */
export class CertificationLandingBody extends Interaction {
    static selector = ".o_cc_landing_richtext";
    dynamicContent = {
        ".carousel-control-prev": { "t-on-click.prevent": this.onPrev },
        ".carousel-control-next": { "t-on-click.prevent": this.onNext },
        ".carousel-indicators a": { "t-on-click.prevent": this.onIndicator },
        ".modal .btn-close": { "t-on-click.prevent": this.onClose },
        ".accordion .collapse": { "t-on-show.bs.collapse": this.onAccordionShow },
    };

    start() {
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        for (const el of this.el.querySelectorAll(".carousel")) {
            // website.carousel_slider matches every .carousel too. Without a
            // data-bs-interval (stripped from the body) it marks the carousel
            // data-bs-ride="false" and creates the Bootstrap instance paused;
            // getOrCreateInstance then hands that instance back and ignores
            // the options below, which left the page on its first slide.
            // Whichever interaction starts first, the instance is rebuilt.
            const ride = reducedMotion ? false : "carousel";
            el.dataset.bsRide = String(ride);
            window.Carousel.getInstance(el)?.dispose();
            new window.Carousel(el, { ride, interval: 5000 });
            // Looked up again: the core interaction disposes the same instance.
            this.registerCleanup(() => window.Carousel.getInstance(el)?.dispose());
            // Bootstrap moves the "active" indicator by data-bs-slide-to,
            // which the sanitizer removed: follow the slide by position.
            this.addListener(el, "slid.bs.carousel", (ev) => {
                this.markActiveIndicator(el, ev.to);
            });
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
        links.forEach((link, position) => {
            link.classList.toggle("active", position === index);
        });
    }

    onAccordionShow(ev) {
        const accordionEl = ev.target.closest(".accordion");
        for (const openEl of accordionEl.querySelectorAll(".collapse.show")) {
            if (openEl !== ev.target) {
                window.Collapse.getOrCreateInstance(openEl, { toggle: false }).hide();
            }
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
