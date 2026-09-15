Each commercial zone of the platform (Guanarteme, Tamaraceite, Lomo los
Frailes) has a manager who looks after its shops: sees them and their
contacts, organises the zone's events and writes to its members. This module
brings that profile back as one plain group, **ZCA Manager**.

Ticking **ZCA Manager** gives a user Contacts (with creation), Events (the
whole app, publishing included), Email Marketing and Discuss. It gives no
Sales, no Products, no Inventory, no Purchases, no Invoicing and no CRM.

The zone is not a setting of the group: it is the user's **session
company**. A manager is a user whose company is the zone company and whose
only allowed company is that one. From there:

- **Companies**: a *Companies* entry under Contacts lists the zone company
  and every shop of that zone (`commercial_zone`), read only.
- **Contacts**: only the contacts of the zone. Nothing to add here:
  `zone_company_ownership` already puts the zone company on every contact
  of the zone's shops, and core's multi-company rules do the rest. A contact
  the manager creates belongs to the zone.
- **Events** default to the zone's website, so they are not listed on the
  other zones' sites.
- **Events**: write, create and delete only on events (and their tickets
  and registrations) of the zone company; an event with no company stays
  readable but is nobody's to edit. A manager's new event is always the
  zone's.
- **Email marketing**: the mailings and mailing lists created by, or
  assigned to, the zone's staff, and the mailing contacts subscribed to
  those lists or created by that staff. The blacklist and the opt-out
  reasons are readable and never edited.
- **One zone per manager**: a user with the group must have the zone
  company as their only allowed company; anything else is refused.
- **Discuss**: the manager is seated in the chat channel of their zone.

It is a group, not a role: nothing is recomposed behind anyone's back. It is
not implied by *Comercios* and not handed to new users; an administrator
ticks it.

The module also owns one menu gate in replace form: *Website ▸ Site ▸
Content ▸ Products*, which core ships open to every internal user, is
restricted to salesmen and website designers.
