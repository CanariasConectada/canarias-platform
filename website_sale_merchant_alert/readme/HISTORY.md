## 19.0.1.1.0 (2026-09-25)

- Web push to the phone of every shop user with a registered device when
  the website receives an order: title "New order S0001", body with the
  shop, the amount and the customer, in the user's language. The push is
  queued (`mail.push` plus the core push cron), so an order that rolls
  back never pushes and the checkout never waits on the push services.
  `_trigger()` wakes the cron right after the commit, so the phone
  normally rings within seconds.
- Shop users now include users who have the shop as an allowed company;
  platform administrators only for the shop that is their main company.
- The alert also fires when a payment ends a checkout without confirming
  the order (wire transfer, pending card payment), once per order
  (`merchant_alert_sent`). The flag is only set once the alert went out,
  so a failed alert is retried by the next trigger, and the order row is
  locked first so two workers cannot both alert. Website orders already
  confirmed or cancelled are marked as alerted on update.
- A failing alert or push now runs in a savepoint, so it cannot abort the
  checkout transaction.

## 19.0.1.0.0

- Email the shop and subscribe its staff when a website order is confirmed.
