- Data migration of the production rows of `memoria.viva.historia` and
  `lugares.interes.historia` (and their taxonomies and likes) into the
  fused models. The field mapping is documented in the reform PR.
- Decide whether a public submission form is still wanted; if so, build it
  as a proper `website.form` flow instead of the legacy JSON API.
- Optional map view of geolocated items (latitude/longitude are kept).
