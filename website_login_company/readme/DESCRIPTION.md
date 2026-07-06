When a user logs in through a website whose company differs from their
default company, this module sets the active company cookie (`cids`) to the
website company, so each merchant lands directly in their own company
context on their microsite. The other companies the user has access to
remain available in the company switcher, just not selected.

This module replaces a legacy hand-patch of the Odoo core file
`addons/web/controllers/home.py` (`Home._login_redirect`) with a proper
installable addon:

* The cookie is only forced when the user actually has access to the
  website company; otherwise the standard Odoo behavior is kept.
* It is a strict no-op when there is no website in the request (XML-RPC,
  hosts that match no website domain, databases without a website), which
  fixes the historic HTTP 500 on login in websiteless contexts.
* Any unexpected error is logged and swallowed: the login flow never
  breaks because of the company cookie.
