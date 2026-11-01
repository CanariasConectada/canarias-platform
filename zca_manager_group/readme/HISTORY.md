## 19.0.1.1.0 (2026-09-21)

- The *Companies* entry under Contacts opens grouped by **Commercial zone**,
  the way an administrator looks at Settings ▸ Companies: trade name,
  company name, commercial zone, contact, category and branches, with only
  the manager's zone in it. The group-by is the `res_company_zone` search
  filter switched on by default, so `res_company_zone` is now a direct
  dependency. No view of its own and no access widened: the list, the
  search view and the form are the administrator's, read only.

## 19.0.1.0.0 (2026-09-15)

- First version: the **ZCA Manager** group (contacts, events, email
  marketing, discuss; no sales, no products), the *Companies* entry under
  Contacts filtered to the manager's zone, the mailing rules, the zone
  website as default of a new event, the seat in the zone chat channel and
  the gate on *Website ▸ Site ▸ Content ▸ Products*. Rules that close what
  the implied groups leave open: mailing contacts and subscriptions of the
  zone only, blacklist and opt-out reasons read only, events (tickets,
  registrations) of the zone only for write, create and delete; the zone
  company forced on a manager's new event; one zone per manager enforced.
