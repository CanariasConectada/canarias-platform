Until the user roles were retired, "make this person a merchant" was one
gesture. This module brings the gesture back as a plain group, **Comercios**,
which implies the nine groups the old merchant role implied — the same list,
read back from the snapshot taken before the roles were uninstalled.

It is a group, not a role: nothing is recomposed behind anyone's back.
Ticking it grants those nine; a permission granted by hand on top of it
stays; unticking it takes away only what it gave.

The group is also handed to **every new internal user**, through Odoo's own
`base.default_user_group` hook.
