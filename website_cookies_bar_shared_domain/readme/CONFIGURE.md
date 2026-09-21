*Settings ▸ Technical ▸ System Parameters*, key
`website.cookies_bar_shared_domain`.

- Value: the bare registrable domain, e.g. `example.com`. No scheme, no path,
  no port. A leading dot is accepted and ignored. An internationalised name
  must be given in punycode.
- Refused: a single label (`es`, `localhost`), an IP address,
  public-suffix-like pairs such as `co.uk` or `com.es`, and a short explicit
  list of well-known multi-tenant suffixes (`github.io`, `gitlab.io`,
  `blogspot.com`, `vercel.app`, `netlify.app`, `herokuapp.com`, `pages.dev`,
  `web.app`, `firebaseapp.com`, `azurewebsites.net`, `cloudfront.net`,
  `amazonaws.com`, `odoo.com`). A domain registered *under* one of them
  (`myshop.github.io`) is accepted.
- **That check is a heuristic**, a convenience for the administrator. The
  real enforcement is the browser's Public Suffix List: a browser refuses a
  cookie scoped to a public suffix, and the module then falls back to a
  host-only cookie, i.e. core's behaviour.
- **To switch the feature off, empty the value. Do not delete the record**:
  it is shipped as `noupdate` data and an emptied value survives upgrades.

The module ships the parameter set to `canariasconectada.es`. On any other
host the value is inert, so it is harmless on lab or development databases.

Every website sharing the consent must publish the same cookie policy.

Leave the parameter empty if tenants can run third-party scripts you do not
control on their sites (see *Known limitations* in the roadmap).
