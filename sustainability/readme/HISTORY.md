## 19.0.2.0.0

OCA-style reform, mirrored with `silver_economy` (see that module's
HISTORY for the full shared-bug analysis). Highlights specific to this
module:

* **Coexistence with `silver_economy` fixed.** Shared method names on
  `survey.user_input` no longer clobber each other: parameters are read
  through the cooperative hook
  `survey.survey._get_certification_config()`, and QWeb rewrites of the
  shared survey templates now use the common `is_certification_survey`
  flag. The hard cross-reference to `survey.is_silver_economy` is gone:
  the module installs standalone.
* The *Instructions* menu pointed to `/sostenibilidad/instructions` while
  the controller serves `/sostenibilidad/instrucciones` (404 from the
  menu). Fixed.
* The microsite certification card described Silver Economy practices
  ("Accesibilidad, Atención personalizada, Servicio y adaptación al
  colectivo" — copy-paste leftover); it now lists sustainability practices.
* The evaluations list showed no certification columns (they belonged to
  silver_economy's view and were hidden outside its context); the module
  now contributes its own columns and the manual-override *Audit* page.
* View xmlids inherited from silver_economy by copy-paste
  (`*_inherit_silver`) renamed; the migration removes the orphan views.
* Same shared fixes as silver_economy: missing `UserError` import,
  threshold boundary logic, durable manual override
  (`override_scoring_total`), one-shot reminder crons, automatic company
  badge recomputation via `certification_input_ids`, dead code removal,
  English source strings with Spanish catalog, OCA manifest/readme layout
  and tests.

## 19.0.1.4.1

Menu and access gated by the `group_sustainability_user` group; migration
assigns the group to existing internal users.
