- Migrate the few production records of the legacy modules (about three
  Silver Economy evaluations; sustainability is nearly empty). Outline:
  1. Install `company_certification`; uninstall `silver_economy` and
     `sustainability` afterwards.
  2. Point the seeded `certification.type` records at the existing
     production surveys (or keep the seeded questionnaires and re-link the
     old `survey.user_input` rows via `survey_id`).
  3. `survey.user_input.company_id` values survive uninstall only if the
     column is preserved: copy `company_id`, `test_entry=False` evaluations
     before uninstalling, or map them by `partner_id`.
  4. Re-assign users from the legacy groups (`silver_economy.group_silver_user`,
     `sustainability.group_sustainability_user`) to the new seeded groups.
  5. Run one evaluation recompute (`_refresh_company_certification`) to
     rebuild `res.company.certification`.
- Recreate the public training pages (Formaciones / Instrucciones) as
  website pages if the content is still wanted.
- Notification emails could move to the type record (templates per
  vertical) if verticals ever need different wording.
