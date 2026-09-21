- A shop served on its **own custom domain** cannot share the consent:
  browsers do not allow a cookie to span registrable domains, and working
  around that would mean cross-site tracking techniques this module will not
  use. Such a shop keeps core's per-host consent.
- While a visitor still holds a stale host-only consent on a host **and** a
  different shared one, the server renders that first page view with
  whichever the browser sent first (third-party script blocking included).
  The frontend removes the host-only cookie on that same page view, so the
  next request is consistent.
- `consent_cookie_patches.js` (the wiring into `cookie.set` and
  `CookiesBar.setup`) has no automated test: the repository has no browser
  test runner. The helpers it calls are executed in `node` by the test suite.
- The public-suffix check is a heuristic (see CONFIGURE).
