## 19.0.1.2.0 (2026-09-25)

* Importer: second format, the consultants' tracking list. Every sheet with a
  business-name header is read (columns recognised by their header text) and
  the rows of one business are merged across sheets. Address, zone, phone,
  e-mail and contact person fill new task fields; the assigned consultant
  becomes the assignee when exactly one field consultant has that name (a
  property otherwise); the latest visit-round date is the planned visit
  (``date_deadline``) and the number of rounds the *Intentos de contacto*
  property; every other named column becomes a task property of the phase.
  Same matching and review list as the checklist, plus rows naming a task
  already in the phase. Contact fields, date and assignee only fill blanks
  on re-import. Sheets with credentials and personal ID columns are never
  read into Odoo.
* Re-imports keep the property values that do not come from the sheet (both
  formats); imported tasks are no longer assigned to the importing manager.
* Daily views: *Project > Field visits > My visits / All visits* with a list
  of whom to visit (zone, address, Google Maps link, contact, phone, planned
  visit, last visit, *Log visit* button), kanban and calendar; *My visits*
  filter and *Zone* grouping in the task search.
* Reminders: a *Field visit* activity for each assigned consultant on the
  planned date, following date and assignee changes; *Log visit* takes the
  next visit date and closes the current reminder.
* Access: the platform administrators (*Settings* access) become *Field
  visit manager* once, at install or at this upgrade, unless somebody was
  appointed already.

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
