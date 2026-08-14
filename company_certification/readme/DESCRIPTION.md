Parameterizable company certification seals built on the native Survey app.

This module fuses the legacy `silver_economy` and `sustainability` modules
(near-identical clones) into a single engine. Each vertical is a
`certification.type` record that parameterizes:

- the survey used as questionnaire,
- the security groups that gate every menu and record,
- the Bronze / Silver / Gold score thresholds,
- the retry cooldown, seal validity and renewal reminder timing,
- the badge image and texts shown on the company microsite.

Adding a third vertical requires zero code: create its two groups, its
survey and one `certification.type` record. The backend menu (root menu +
"My Evaluations" + "New Evaluation"), gated to the vertical's user group, is
generated automatically.

Certification state is stored per company in `res.company.certification`
records, kept in sync from the evaluations and searchable by other modules
(e.g. the website directory bridge).
