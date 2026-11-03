## 19.0.1.5.0 (2026-09-07)

* **The cross is now the directory's, not this card's**: the selected seal
  calls `website_directory.directory_filter_chip` instead of drawing its
  own `fa-times`, so it shares the accessible "Remove filter: …" label,
  the focus ring and the 24px cross with every other filter section. The
  visible affordance is unchanged — this card is the one the visitor
  already understood, and the rest were made to match it.

## 19.0.1.0.0 (2026-07-06)

First release. Bridge between `website_directory` and
`company_certification`, built entirely on the directory extension hooks
(no core template surgery):

* Certification badge pills on directory cards and list rows for companies
  holding a seal in force.
* A **Certifications** filter card in the directory sidebar
  (`directory_sidebar_extra` hook), driven by the `?certification=<code>`
  query parameter through `_get_extra_filter_domain()` /
  `_get_extra_pager_args()`.
* Auto-installed when both modules are present; neither module depends on
  the other.
