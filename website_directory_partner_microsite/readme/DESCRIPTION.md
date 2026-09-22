Puts the directory category on the merchant's own page-content screen.

`res.company.set_own_directory_category` has been able to do this since July,
and `/mi-comercio` is a working page built around it — but nothing links to
that page. No website menu points at it and no button reaches it, so in
practice the category was the merchant's to change only if somebody told them
the URL. 49 businesses have no category at all.

This module adds the same field to **Website › Configuration › Page content**
and saves it through that very same method: the company is resolved from the
session, exactly one field is written, and a "view" category — a folder that
only groups other categories — is refused.

Deliberately NOT added to the page-content whitelist, which is written
straight onto `res.company` with sudo: the category needs three checks that
whitelist knows nothing about, and they already live in one place.
