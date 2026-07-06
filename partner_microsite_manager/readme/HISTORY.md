## 19.0.1.0.0 (2026-07-06)

Full OCA-style rebuild of the legacy `partner_microsite_manager` (1.3.9)
for the Doodba-based architecture:

* Microsite content moved from `res.partner` to `res.company` (merchant =
  company with its own website).
* Static HTML generation replaced by a dynamic QWeb homepage template;
  the write-triggered view-rewriting sync is gone.
* Dropped: custom raw-HTML homepage toggle, logo / favicon / social link
  duplication (native per-website settings), theme footer patching,
  hardcoded attachment and website ids, `theme_corporate_multi`
  dependency, embedded `crm.lead` contact form (links to `/contactus`
  instead), "open now" JavaScript badge.
* New: explicit **Publish Homepage** action, opening-hours format
  validation as a real constraint, demo data, English source with Spanish
  translation, full test suite.
