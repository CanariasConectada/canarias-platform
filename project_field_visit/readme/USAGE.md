Give the consultants the *Field visits / Field visit consultant* access and
whoever runs the programme *Field visit manager*. Project access alone does
not show field-visit projects.

1. Project > Field visits > Import spreadsheet. Create the phase project
   from the dialog (for example "Consultoría puerta a puerta — Fase I") or pick
   an existing one with *Door-to-door field visits* enabled in its settings.
2. Upload the .xlsx (or .csv) and keep *Dry run* ticked the first time: the
   summary shows how many rows match a platform company (by subdomain, exact
   name or similar name) and which ones will become prospect contacts.
3. Untick *Dry run* and import. Section rows become stages, each business a
   task; the *Observaciones* column is posted as the first chatter note.
4. Consultants open a task (kanban shows the business, microsite and
   checklist) and press **Log visit** after each visit.

The consultants' tracking list (the workbook they keep by hand, several
sheets) is imported the same way, into the same phase project: each business
gets its address, zone, contact, phone, planned visit and follow-up columns.
Import it after the checklist so both land on the same tasks.

The assignee of a business comes from its *ASIGNACION* (or *Consultor*)
column. A sheet named after a consultant (``BERTA``, ``David``: full or first
name of exactly one active field consultant) assigns its rows whose column is
empty, or all of them when the sheet has no such column. A business listed on
several consultants' sheets is assigned to all of them; re-imports add
assignees and never remove one.

Headers are matched by their text. Columns that look like credentials
(password, *clave*, PIN, user login) make the whole sheet skipped, and
personal identifiers (NIF/CIF/DNI/NIE, IBAN...) are never read; the summary
lists them under *Columns ignored for privacy*. A sheet whose only name column
is a bare *Nombre* is read only when at least half of its names are known
businesses; otherwise rename the column *Nombre comercial*. Rows of one
business in several sheets are merged in sheet order: keep the master list
first. A re-import only fills what is empty on the tasks; tick *Overwrite
values from the spreadsheet* when the sheet must win.

Every day, *Project > Field visits > My visits* lists the businesses assigned
to you with their address (*Map* opens Google Maps), phone and planned visit;
switch to the calendar to see the week. Managers also get *All visits*,
grouped by zone. The planned date of a task is a
reminder in your activities; *Log visit* can set the next one.

To check that every merchant has all its information, filter the visits by
*Incomplete information*: each task linked to a platform business lists what
its microsite lacks (homepage images, intro, about, services and strip
texts, logo, phone, e-mail, address, opening hours, business category). The
list is refreshed every night; managers can select tasks and run *Action >
Refresh microsite status* after a merchant updates the site.

For the next phase, create a new project, enable *Door-to-door field
visits* and add its own fields from the task form (*Add Properties*).
