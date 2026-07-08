* The taxonomy is seeded once, at install time. There is no automatic
  reconciliation on module update: business categories added to
  `DEFAULT_CATEGORIES` in a later version are **not** back-filled into
  existing databases — by design, so user edits are never overwritten. A
  future version may add an opt-in re-seed action for administrators.
* Category names are Canarias marketplace business data and are kept in
  Spanish on purpose; they are not translated.
* The module owns no view of its own: the tree is managed through the
  `res_company_category` maintainer UI. A dedicated "Canarias taxonomy"
  action could be added if the seeded set needs to be curated apart from
  user-created categories.
