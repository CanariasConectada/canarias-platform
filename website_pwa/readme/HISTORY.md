## 19.0.3.0.0 (2026-09-25)

- Backend: a "Canarias Conectada" home entry in the systray (house icon) and in
  the user menu, for every internal user. Inside the installed app the backend
  (Discuss above all) had no way back to the website short of killing the app.
  It links to `/` on the current host, which stays inside the app's scope.
- New `website_pwa.pwa_install_quick_access` template: a compact "Download
  Canarias Conectada" install card that other pages (the login pages first)
  can `t-call`. It uses the snippet's classes, so `pwa_install.js` drives both.
- `pwa_install.js`: reveals and hides EVERY install card on the page instead of
  the first one only; exports `isIOS()` and `isStandalone()`; detects iPadOS,
  which reports itself as a Mac and was sent down the Android branch; hides
  the cards on `appinstalled`; registering the worker can no longer throw or
  leave an unhandled rejection when the browser blocks service workers.
- Tests pinning the manifest, the website worker and core's backend worker to
  each other: start_url inside the scope, `Service-Worker-Allowed` equal to
  the scope, the page registering the served worker with that scope, `/odoo`
  nested inside the app's scope and core's worker kept at `/odoo`.
