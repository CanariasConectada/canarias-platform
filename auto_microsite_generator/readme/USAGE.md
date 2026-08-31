## Creating a microsite

Creating a company does **not** publish its website. The company form shows
"This shop has no microsite yet" with a **Create Microsite** button, which
asks for the subdomain, shows the exact address the site will answer at, and
only then provisions it.

That order is the point. DNS here is manual — there is no registrar API and
the wildcard certificate is renewed by hand — so the hostname has to be
decided by a person and pointed at the server before anything starts serving
on it. A website born on a hostname nobody registered is a dead link with a
merchant attached to it.

A caller who already knows the answer is never asked: pass the subdomain to
`create` and the microsite is provisioned in the same transaction.

```python
env["res.company"].create({"name": "Neveri", "microsite_subdomain": "neveri"})
```

To provision or refresh the microsite of an existing company from a shell or
a server action:

```python
company.microsite_subdomain = "neveri"
company._auto_generate_microsite()
```

This call is idempotent and never overwrites migrated content.

## What a new microsite is born with

* the `website` record linked to the company;
* a homepage at `/`, the rich corporate one when
  `partner_microsite_manager` is installed;
* the standard top menu — Home, Shop, Directory — **written in every
  installed language**. The wording is seeded from the estate rather than
  left to the machine translator: "Comercio" out of context is the noun, not
  the directory, and engines return Trade/Handel/Commerce for it;
* the "Zonas Comerciales" dropdown that links the network together;
* the cookies bar, so consent is asked before optional cookies are set;
* opening copy in the microsite content fields, so the merchant sees a real
  page instead of an empty shell.

## Configuration

System parameters (Settings > Technical > Parameters > System Parameters):

* `auto_microsite_generator.enabled` (default `True`): set to `False` to turn
  the automatism off globally without uninstalling the module.
* `auto_microsite_generator.subdomain_mode` (default `ask`, `noupdate`):
  * `ask` — a company created without a subdomain gets **no website**. It
    waits on the company form until somebody names one.
  * `auto` — the subdomain is derived from the company name, as before. Use
    it for a bulk import, where answering the question 200 times is not an
    option. Clashes are resolved by suffixing (`panaderia-2`) rather than by
    failing, so no company is left without a site.

  Anything else reads as `ask`: a typo must fail towards being asked, never
  towards publishing on a hostname nobody registered.
* `auto_microsite_generator.domain_suffix` (seeded to `.canariasconectada.es`,
  `noupdate`): appended to the subdomain to build the website domain.
  Emptied on purpose, websites are created without a domain and a warning is
  logged, because such a site is unroutable until the parameter is set again.

The automatism can also be skipped per transaction by passing
`no_microsite_auto=True` in the context of `res.company.create` (used by the
data migration when it manages websites itself).

Companies whose name matches a structural/umbrella pattern (`zona comercial`,
`canarias conectada`, `my company`) never receive a microsite.
