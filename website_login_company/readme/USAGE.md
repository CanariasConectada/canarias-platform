1. Assign a company and a domain to each website (Website > Configuration >
   Settings, or the `company_id` and `domain` fields of the website).
2. Make sure the users that should land in that company have it among
   their allowed companies.
3. When such a user logs in from that website domain, the website company
   becomes the active company automatically.

No configuration is needed: if the host does not match any website domain,
or the user has no access to the website company, the standard Odoo login
behavior applies.
