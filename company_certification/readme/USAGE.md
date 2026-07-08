## For evaluated companies (internal users in a vertical's group)

1. Open the vertical's menu (e.g. *Silver Economy*).
2. Use *New Evaluation* to start the questionnaire. The cooldown of the
   last attempt is enforced per company.
3. Follow *My Evaluations* to continue or review attempts.
4. When the score reaches a threshold, the seal is awarded, the company
   microsite shows the certification section, and a congratulation email
   is sent.

## For certification managers

- *Certifications > Certification Types*: configure thresholds, timing,
  groups, survey and website texts of each vertical.
- *Certifications > All Evaluations*: audit every attempt. The
  *Certification* tab of an evaluation allows a manual level override with
  a reason; the audit trail (who, when, why) is stamped automatically.
- *Certifications > Company Certifications*: the seals currently in force.

## Adding a new vertical (no code)

1. Create a user group and a manager group (Settings > Groups). The user
   group must imply *Certification User (base)*; the manager group must
   imply the user group and *Certification Manager*.
2. Create the survey (scored questions).
3. Create a *Certification Type* pointing at the groups and the survey.
   The gated backend menu is generated automatically.
