Shared embedded map for the public pages of the Canarias Conectada platform.

It adds one helper on `res.partner`, `_canarias_map_embed_url()`, that turns
the partner's street/city into a key-less Google Maps `output=embed` URL
(and returns `False` when the address is not usable), plus a reusable QWeb
template `website_map_embed.map_iframe` that renders it as a lazy, responsive
iframe. Merchant microsites and event pages both use it, so every map on the
platform looks and behaves the same.
