Provision a website, a homepage and the standard menu automatically when a
company is created.

In the Canarias Conectada platform every merchant is a `res.company` with
its own website (native Odoo multi-website). When a company is created this
module provisions the microsite scaffolding so an operator never starts from
a blank website:

* creates the `website` record linked to the company (unless it already has
  one);
* installs a default homepage at `/` with a lightweight welcome template;
* ensures the standard top-menu entries (Home, Shop, Directory) exist.

The generation is **non-destructive and migration-aware**. Website content
brought in "as is" by the data migration (COW pages, views and menus anchored
to `canarias_mig.*` external IDs) is detected and never overwritten: the
generator only creates what is missing. Rich, editable microsite homepages
are the job of `partner_microsite_manager`'s *Publish Homepage* action, which
overwrites the homepage only on explicit request — never in this automatic
flow.
