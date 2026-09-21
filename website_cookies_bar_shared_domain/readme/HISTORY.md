## 19.0.1.0.0 (2026-09-21)

- First version: the cookies bar consent is shared across the subdomains of
  the domain set in `website.cookies_bar_shared_domain`.
- Two coexisting consents are settled on their values: a refusal beats an
  acceptance whatever their age, otherwise the most recent wins; the winner
  lands in the shared cookie with the lifetime its own `ts` leaves it.
- The parameter also refuses a short list of well-known multi-tenant
  suffixes (`github.io`, `herokuapp.com`...).
- A stored object without `optional` is a refusal, as it is for core, and
  takes part in the resolution as such.
