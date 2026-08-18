The module works automatically: create a company (Settings > Companies, or
through the data migration) and its microsite is provisioned right away.

To provision or refresh the microsite of an existing company from a shell or
a server action:

```python
company._auto_generate_microsite()
```

This call is idempotent and never overwrites migrated content.

## Configuration

Two system parameters (Settings > Technical > Parameters > System Parameters):

* `auto_microsite_generator.enabled` (default `True`): set to `False` to turn
  the automatism off globally without uninstalling the module.
* `auto_microsite_generator.domain_suffix` (seeded to `.canariasconectada.es`,
  `noupdate`): a default website domain is built from the company name, such
  as `https://bakery.canariasconectada.es`, so a new microsite is born
  routable. Emptied on purpose, websites are created without a domain and a
  warning is logged, because such a site is unroutable until the parameter is
  set again.

The automatism can also be skipped per transaction by passing
`no_microsite_auto=True` in the context of `res.company.create` (used by the
data migration when it manages websites itself).

Companies whose name matches a structural/umbrella pattern (`zona comercial`,
`canarias conectada`, `my company`) never receive a microsite.
