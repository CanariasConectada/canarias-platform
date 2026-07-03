Silver Economy evaluation and certification for the companies of the
Canarias Conectada marketplace, built on top of the `survey` app.

Internal users answer a 40-question questionnaire about their company and,
depending on the score, the company is awarded a Bronze, Silver or Gold
badge. The badge:

* is shown on the company form and list views (backend),
* decorates the company entry in the public directory
  (`website_directory`),
* renders a certification card on the company microsite, including the
  score and a configurable list of "positive items" (highlights taken from
  well-answered questions).

Badges expire after a configurable validity period (1 year by default).
After a failed attempt, the company must wait a configurable cooldown
(3 months by default) before retrying. Daily crons send one-shot email
reminders when the retry becomes available, shortly before renewal is due,
and when a badge expires.

Certification managers can override the computed score keeping a full audit
trail (original score, author, date, reason), and the override survives any
scoring recomputation.

This module coexists with its twin `sustainability`: both extend
`survey.user_input` with the same shared fields and cooperative method
bodies, so each questionnaire type is always scored with the thresholds of
its own module regardless of the module load order.
