Phase 3 (final) of moving the Canarias Conectada "Comunidad" experience into
the Discuss backend: the standalone community pages that `website_pwa_chat`
serves are retired behind the `/community` door that `discuss_community`
opened in Phase 1.

What installing this module changes
-----------------------------------

- **`/chat` and `/chat/<id>` answer `301 Moved Permanently` to `/community`**
  on the website(s) that used to serve them. The microsites that never served
  the chat keep answering 404, exactly as before -- the redirect must not
  turn a deliberate "this site does not serve the chat" into a live URL on
  every storefront.
- **The "Comunidad" menu entry points at `/community`**, keeping the two URL
  shapes the `/chat` entry had: a relative path on the website that serves
  the chat, an absolute URL to that host on the zone portals that live on
  their own subdomains.

From `/community`, `discuss_community` routes by identity: internal sessions
(community members, staff) land in the Discuss backend, anonymous visitors
get the guest/signup card, and portal sessions get the same card with a note
-- the loop-free arrangement, since `/chat` now points back here.

What it deliberately leaves alone
---------------------------------

The support feature is not the community and keeps working exactly as it is:

- `/chat/soporte` and `/chat/soporte/identificarme` -- the full support page,
  the floating window and its lazy iframe all navigate there;
- the `/website_pwa_chat/messages` and `/website_pwa_chat/pending` jsonrpc
  routes -- the support conversation's live catch-up and held-message card;
- the floating bubble and `website._chat_support_url()`;
- the backend Soporte queue and its Discuss category.

Why a bridge module
-------------------

So the retirement is an explicit, reversible decision. `website_pwa_chat`
keeps serving the standalone pages wherever this module is not installed,
and having Phase 1's door and the standalone pages side by side stays a
supported state (it was production's state for weeks) -- which is also why
this module is **not** `auto_install`.
