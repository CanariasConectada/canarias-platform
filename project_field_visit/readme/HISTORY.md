## 19.0.1.1.0 (2026-09-25)

* Access: new groups *Field visit consultant* and *Field visit manager*.
  Global record rules keep field-visit projects and tasks away from everybody
  else (plain project users included); the business fields, smart buttons
  and visit dialog are for consultants, the importer and the project switch
  for managers.
* One task per business and phase is enforced in the database; the business
  contact must be the business's own contact or an importer prospect.
* Importer: candidates exclude the platform, zone, archived and owning
  companies; a subdomain whose company name does not agree, a slug shared by
  several websites, a row naming an archived company or an unsure prospect
  rename goes to a review list instead of being linked. Prospects keep a
  stable key and annex number; same-named prospects with different annex
  numbers stay apart. Files over 10 MB and sheets over 5000 rows or 60
  columns are refused; rows are streamed.

## 19.0.1.0.0 (2026-09-25)

* First version: field-visit projects (one per phase, checklist as task
  properties), visited business and microsite on the task, *Log visit* dialog
  with evidence attachments, *Field visits* smart buttons on company and
  contact, and the phase I spreadsheet importer.
