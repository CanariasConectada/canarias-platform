Known limits, written down so nobody has to rediscover them.

- **It cannot cover the first paint, and nothing in this module can.** The
  frontend stylesheet is render-blocking, so the browser paints nothing at all
  until it has arrived. Every affordance here lives in that same HTML and is
  therefore also waiting on it. On this platform the wait is roughly 5.7 MB,
  because nginx ships `gzip on` with `gzip_types` commented out and the default
  covers `text/html` alone: CSS and JS travel uncompressed. Enabling the
  matching MIME types is the fix for the white screen; this module only makes
  the rest of the journey legible.

- **The busy button is never revived without a page load.** Deliberate. A form
  that looks idle again while its first request may still land is how double
  submissions happen, so the 20 second ceiling changes the curtain's wording
  rather than clearing the state.

- **The curtain is light-only.** It derives its background from
  `--o-cc-card-bg`, and the card it covers has no dark variant, so a dark
  curtain would lift onto a light page. It follows the card, and will follow it
  again if that card ever gains a dark theme.

- **`inert` is used without a polyfill.** Supported across current Chrome,
  Firefox and Safari. On an older engine the curtain still covers the form
  visually; only the keyboard trap guard is lost.
