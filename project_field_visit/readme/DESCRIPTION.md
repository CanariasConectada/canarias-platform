Support for the consultants who go door to door, business by business,
documenting the programme, with everything kept next to the microsites and
companies of the platform.

- **One project per phase.** The fields the consultants fill in for a phase
  are the native task properties of its project, defined from the interface.
  The next phase is a new project with its own fields: no code change.
- **One task per business.** A task is linked to the visited business
  (`business_company_id`), its contact and its microsite (with an *Open
  microsite* button). Businesses that are not on the platform yet are linked
  through a contact only.
- **Log visit.** A phone-friendly dialog posts each visit to the task chatter
  (date, consultant, outcome, notes) with the photos and documents taken on
  the spot, and can move the task to another stage.
- **Field visits** smart buttons on the company and on the contact list the
  tasks of that business across every phase.
- **Spreadsheet import.** The phase I spreadsheet (one section per status)
  becomes stages, tasks and checklist values; the consultants' tracking list
  (several sheets, recognised by their headers) adds address, zone, contact,
  planned visit, assignee and its follow-up columns as properties.
  Re-importing updates the same tasks.
- **The consultant's day.** *My visits* (list, kanban, calendar) with the
  address and a Google Maps link, and a reminder activity on each planned
  visit.

**Known limitation.** Access is per programme, not per consultant: a
*Field visit consultant* can open every task of the field-visit projects
(the record rule does not narrow them to their own assignments). The menus
steer consultants to *My visits* and keep *All visits* for managers, which
is enough for a small team that works the whole list together; a team that
must not see each other's businesses needs an assignee-based record rule.

The visited business usually belongs to another company than the consultant.
Its name and microsite URL are stored on the task, so a consultant limited to
the programme company reads the task without reading the business records.
