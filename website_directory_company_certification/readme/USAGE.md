- The bridge auto-installs once both `website_directory` and
  `company_certification` are present; there is nothing to configure.
- Companies holding a certification **in force** (not expired, level other
  than *none*) show a coloured badge pill per seal on their directory card
  and list row (bronze/silver/gold colour coding).
- The directory sidebar gains a **Certifications** filter card listing every
  `certification.type`. Selecting one narrows the listing to companies
  holding that seal, through the `?certification=<code>` query parameter.
- The filter is stateless and shareable: the active seal is encoded in the
  URL and preserved across pager pages.
