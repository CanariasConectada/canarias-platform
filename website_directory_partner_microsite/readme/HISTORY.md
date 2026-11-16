## 19.0.2.2.0 (2026-11-03)

History starts here; earlier versions have no entries. For the record:
19.0.2.0.0 made the card carry the trade name typed on `microsite_name`
(measured 2026-09-02: 75 of 205 cards showed the legal name while the trade
name sat right next to it, and every sync pass rewrote hand fixes back).

- `res.company.microsite_title` (from `partner_microsite_manager`
  19.0.2.16.0) now resolves cover title, then trade name (`comercial`),
  then legal name: a shop that leaves the cover title empty gets its sign
  on the cover and in the footer.
- The directory card reads that resolved title instead of `microsite_name`
  alone, so clearing the cover title no longer drops the card back to the
  legal name. Branches resolving to one and the same title keep their
  legal names, as before; archived companies no longer count as twins.
- The card is flagged for a resync when the cover title changes on the
  company or the trade name changes on the partner (Contacts) -- neither
  was a sync trigger before. The post-migration queues one resync of every
  directory company.
