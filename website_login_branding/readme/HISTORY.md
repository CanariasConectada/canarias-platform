## 19.0.2.3.1 (2026-09-25)

- Tests: the login-without-push-APIs browser tests run without a screencast,
  so a frame acknowledged while Chrome closes cannot fail them after the check
  succeeded.

## 19.0.2.3.0 (2026-09-25)

- "Download Canarias Conectada" under the login card (login, signup and reset
  password pages), only on websites with the app enabled: the Android install
  button or the iOS "Share / Add to Home Screen" steps, hidden once running as
  the app; inside the installed app, a "Turn on notifications" button that
  asks for permission from the tap iOS requires, so core subscribes the device
  as soon as the user signs in. Both cards come from `website_pwa` and
  `website_pwa_push`, which this module now depends on.
- Browser tests: the login still submits and signs in when the Push API is
  missing or its accessors throw.
