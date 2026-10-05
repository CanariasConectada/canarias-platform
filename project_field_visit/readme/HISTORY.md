## 19.0.1.4.0 (2026-10-05)

* Microsite completeness on the task: a task linked to a platform business
  shows what its microsite still lacks (*Missing microsite information*,
  from ``partner_microsite_manager``) and whether it is *Information
  complete*, in the form, the kanban card and the lists, with an
  *Incomplete information* filter. Refreshed when the task's business
  changes, every day by a cron (one batched check for all tasks) and by the
  managers' *Refresh microsite status* action. New dependency:
  ``partner_microsite_manager``.

## 19.0.1.3.0 (2026-10-05)

* Importer, tracking list: a sheet whose title names a field consultant (full
  or first name, case and accents ignored, exactly one active user) assigns
  that consultant to its rows with an empty assignment column, so a
  consultant's own sheet needs no *ASIGNACION* column. A value in the column
  still wins over the sheet title. A business on several consultants' sheets
  gets all of them as assignees; a re-import only adds assignees.

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
  already in the phase. A bare *Nombre* column is taken as the business only
  when at least half of its values are known business names. On re-import,
  contact fields, date, assignee and properties only fill what is empty,
  unless *Overwrite values from the spreadsheet* is ticked. Default-deny
  privacy: a credential-looking header (password, *clave*, PIN, login) in or
  above the header row skips the sheet, personal identifiers (NIF/CIF/DNI/
  NIE, IBAN...) are skipped; both are listed in the summary, which also names
  the authoritative (first) sheet.
* Re-imports keep the property values that do not come from the sheet (both
  formats); imported tasks are no longer assigned to the importing manager.
* Daily views: *Project > Field visits > My visits* (and *All visits* for
  managers only) with a list
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
