## 19.0.2.0.0 (2026-08-14)

- A skeleton in the login form slot. Odoo 19 serves the form with Bootstrap's
  `d-none` and only reveals it once the OWL component `web.user_switch`
  mounts, so between the logo and "o continúa como invitado" there is a blank
  box for as long as the frontend bundle takes to boot -- reported with a
  screenshot as happening often. The skeleton stands in that slot and never
  hides the form: Odoo hides it and Odoo reveals it, so the worst this can do
  is linger beside a working form.
