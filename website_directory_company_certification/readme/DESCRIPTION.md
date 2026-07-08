Bridge between `website_directory` and `company_certification`, using the
directory's extension hooks (no core template surgery):

- A certification badge pill on every directory card and list row of
  companies holding a seal in force.
- A "Certifications" filter card in the directory sidebar
  (`directory_sidebar_extra` hook) plus the `?certification=<code>` query
  parameter handled through `_get_extra_filter_domain()` /
  `_get_extra_pager_args()`.

Auto-installed when both modules are present; neither module depends on
the other.
