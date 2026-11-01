# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website PWA Chat: Community Redirect",
    "version": "19.0.1.0.0",
    "category": "Website",
    "summary": "Retires the standalone community pages: /chat and /chat/<id> "
    "permanently redirect to the /community door",
    "description": """
        Phase 3 (final) of moving the "Comunidad" experience into the Discuss
        backend: the standalone community pages are retired in favour of the
        /community door that discuss_community opened in Phase 1.

        A bridge module on purpose. website_pwa_chat keeps serving the
        standalone pages wherever this module is not installed, so the
        retirement is an explicit, reversible install -- not a side effect of
        having both parents in the same database (hence no auto_install).

        What it changes:

        - /chat and /chat/<id> answer 301 Moved Permanently to /community,
          on the websites that used to serve them. The 217 microsites that
          never served the chat keep answering 404, exactly as before.
        - The "Comunidad" menu entry points at /community, with the same
          relative-on-the-host / absolute-cross-subdomain shapes the /chat
          entry had.

        What it deliberately leaves alone -- the support feature is not the
        community and keeps working exactly as it is:

        - /chat/soporte and /chat/soporte/identificarme (full page, floating
          window and its iframe all depend on them);
        - the /website_pwa_chat/messages and /website_pwa_chat/pending
          jsonrpc routes (the support conversation's live half);
        - the floating bubble and `website._chat_support_url()`.
    """,
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        # The pages being retired and the menu-entry helpers being repointed.
        "website_pwa_chat",
        # The door the redirects lead to: /community must exist, and its
        # portal branch must be the loop-free card (>= 19.0.1.1.0).
        "discuss_community",
    ],
    "data": [],
    "installable": True,
    "application": False,
    # Explicitly NOT auto_install: having Phase 1 and the standalone pages in
    # one database is a supported state (it was production's state for weeks);
    # retiring the pages is a decision somebody takes by installing this.
    "auto_install": False,
}
