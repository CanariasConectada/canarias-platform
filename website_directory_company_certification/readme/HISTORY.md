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
