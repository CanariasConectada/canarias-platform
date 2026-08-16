# Company Facilities

Publishes what each shop offers — accessibility, payment, parking, service —
on its microsite, grouped into subdivisions and shown with icons.

The catalogue of subdivisions and items is shared and editable from the
interface, so the same wording is written and translated once and reaches all
of the microsites at the same time. Each shop then ticks the ones that apply on
its own company form.

## Usage

**Defining the catalogue** — Website ▸ Configuration ▸ Facilities and services.
"Subdivisions" holds the headings, "Items" holds what a shop can offer. Both
take a Font Awesome 4.7 class as the icon (`fa-wifi`, `fa-wheelchair`…).

Reserved for the *Manage the facilities catalogue* group. On this platform
groups are granted through roles (`base_user_role`); ticking the group on a
user by hand is reverted on the next synchronisation.

**Per shop** — the company form, Microsite page: pick the items and, if the
default heading does not fit, give the block a title of its own.

**Languages** — anything added from the interface goes through the automatic
translation queue like any other content. The catalogue shipped with the module
is translated in its `.po` files instead, and those translations are protected
from the engine.

## Known issues / Roadmap

* No per-zone catalogue: every shop picks from the same list. If a zone ever
  needs items of its own, add a `company_ids`/zone domain rather than a second
  catalogue.
* The block is injected after the About section of the microsite homepage. A
  shop that rebuilt its homepage in the website builder keeps its own layout
  and will not show it.

## Changelog

## 19.0.1.0.0 (2026-08-16)

* First version: catalogue of subdivisions and items with icons, per-company
  selection, and the block on the merchant microsite.

## Contributors

* MikeColangelo
