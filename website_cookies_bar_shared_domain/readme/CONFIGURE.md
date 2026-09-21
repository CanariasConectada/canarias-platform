*Settings ▸ Technical ▸ System Parameters*, key
`website.cookies_bar_shared_domain`.

- Value: the bare registrable domain, e.g. `example.com`. No scheme, no path,
  no port. A leading dot is accepted and ignored. An internationalised name
  must be given in punycode.
- Refused: a single label (`es`, `localhost`), an IP address, and
  public-suffix-like pairs such as `co.uk` or `com.es`. The check is a
  heuristic, not the Public Suffix List; browsers enforce the real list on
  their own and the module then falls back to a host-only cookie.
- **To switch the feature off, empty the value. Do not delete the record**:
  it is shipped as `noupdate` data and an emptied value survives upgrades.

The module ships the parameter set to `canariasconectada.es`. On any other
host the value is inert, so it is harmless on lab or development databases.

Every website sharing the consent must publish the same cookie policy.
