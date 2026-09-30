## Known limitations

- **Trust model (inherent to a `Domain` cookie).** Any script running on
  any `*.<shared domain>` host can write, overwrite or delete the shared
  consent cookie. A tenant able to inject script into its own microsite
  could therefore forge or wipe the platform-wide consent value. The impact
  is limited to the consent flag: no credentials are involved, and Odoo's
  session cookie is `HttpOnly` and host-only, untouched by this module. On
  this platform the operator controls every host under the domain, and the
  refusal-wins rule means the migration path can only narrow a consent,
  never widen it. **Operators who allow untrusted third-party scripts on
  tenant sites should leave the parameter empty.**
- A shop served on its **own custom domain** cannot share the consent:
  browsers do not allow a cookie to span registrable domains, and working
  around that would mean cross-site tracking techniques this module will not
  use. Such a shop keeps core's per-host consent.
- While a visitor still holds a stale host-only consent on a host **and** a
  different shared one, the server renders that first page view with
  whichever the browser sent first (third-party script blocking included).
  The frontend removes the host-only cookie on that same page view, so the
  next request is consistent.
- The test suite executes the shipped `consent_cookie_patches.js` in `node`
  with core's real `patch`, `cookie` and `http_cookie.js`, but with a fake
  `CookiesBar`, `session` and `document`: the real `CookiesBar`/`Popup`
  classes and the bundle's load order are only exercised by a manual browser
  check (the repository has no browser test runner).
- The public-suffix check is a heuristic (see CONFIGURE): the browser's
  Public Suffix List is the real enforcement, and the fallback is a
  host-only cookie.
