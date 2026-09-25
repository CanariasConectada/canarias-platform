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
- *Certification Types > (type) > Items shown on microsite*: the catalogue
  of icons shown under the seal on a certified company's microsite. Each
  item has an icon (Font Awesome 4 name, previewed in the list), a label,
  an optional description and optional triggers:
  - no trigger: every holder of the seal shows it;
  - *Trigger question* + *Minimum score*: shown when the company's
    awarding evaluation scored at least that on the question (2 = a full
    "Yes" in a No/Partially/Yes question);
  - *Trigger answers*: shown when any of those answers was selected;
  - both: either one is enough.

  A seal imported without an evaluation shows every item, or only the
  untriggered ones when *Show every item without an evaluation* is off.
  Archive an item to hide it without losing it.

## Adding a new vertical (no code)

1. Create a user group and a manager group (Settings > Groups). The user
   group must imply *Certification User (base)*; the manager group must
   imply the user group and *Certification Manager*.
2. Create the survey (scored questions).
3. Create a *Certification Type* pointing at the groups and the survey.
   The gated backend menu is generated automatically.
