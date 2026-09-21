Odoo stores the answer to the cookies bar in the cookie
`website_cookies_bar`, written without a `Domain` attribute. Such a cookie is
*host-only*: the browser gives it back to the exact host that set it and to no
other. On a platform that serves many websites as subdomains of one
registrable domain (`example.com`, `shop-a.example.com`,
`shop-b.example.com`...) the visitor is therefore asked to accept cookies
again on every single site.

With this module the consent is written once with `Domain=<shared domain>`,
so accepting (or refusing the optional cookies) on any of those sites applies
to all of them, and so does changing the preference later.

- The shared domain is a system parameter, not code. Empty = core behaviour,
  untouched.
- The `Domain` attribute is only ever used when the current hostname **is**
  the configured domain or **ends with** `.` + that domain. localhost, an IP
  address, a lab host or a shop on its own custom domain keep core's
  host-only cookie.
- A host-only cookie and a shared one can never coexist: every write (and
  every delete) expires the host-only cookie of the current host first. Two
  cookies with the same name are both sent by the browser, and which one is
  read first is an accident of their creation time.
- Visitors who had already answered on some host are migrated on their next
  page view there: their host-only consent is moved to the shared domain
  with the lifetime it had left, and the bar is not shown again.
- When a host-only consent and a shared one coexist with different values,
  the winner is decided on the values, never on where they came from: a
  **refusal** of the optional cookies beats an acceptance whatever their
  age, and between two equal answers the most recent `ts` wins. The winner
  ends up in the shared cookie with the lifetime its own `ts` leaves it
  (never extended) and the host-only duplicate is expired. The asymmetry is
  deliberate: a stale or forged cookie can only ever *narrow* the consent.
  To accept again, the visitor answers the bar, which writes the shared
  cookie directly.
- If the browser refuses the `Domain` cookie, the consent falls back to a
  host-only cookie, which is exactly core's behaviour.
- The website builder is not affected: the cookies bar interaction does not
  run in edit mode, and no view is inherited.

**Privacy.** The consent is shared only between hosts of the same platform,
run by the same operator under one registrable domain and one cookie policy.
Nothing is sent to any third party, and the cookie holds what it holds in
core and nothing more: `{required, optional, ts}`.

**Trust model.** A `Domain` cookie can be written by a script running on
*any* host of that domain. See *Known limitations* in the roadmap before
enabling this on a platform whose tenants may run scripts you do not
control.
