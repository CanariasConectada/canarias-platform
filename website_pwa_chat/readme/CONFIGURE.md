Three switches, all off by default.

- **The website that serves it.** `Sitio web → Configuración → Sitios web`,
  field **Chat de la comunidad**. Turn it on for the main portal and nowhere
  else: the four channels belong to the whole platform, so serving them from a
  merchant's microsite would put another merchant's conversation on their site.
  Until it is on, `/chat` answers 404 everywhere — the intended posture for a
  database with 218 websites.

- **The websites that only link to it.** Field **Enlace a Comunidad**, on the
  three neighbourhood portals (Guanarteme, Lomo los Frailes, Tamaraceite) and
  on nothing else. They live on their own subdomains, so their menu entry is an
  absolute URL built from the `domain` of whichever website has **Chat de la
  comunidad** on. Leave it off on the merchant microsites: a shop's window is
  not a public square, and the link would pull a visitor out of the shop they
  were looking at.

  If the host website has no `domain` filled in, the entry is simply not
  rendered. That is deliberate — an incomplete configuration must cost a
  visitor one tap, not a whole page.

- **The channels.** Installing the module publishes the four channels seeded by
  `discuss_channel_zone`. A fifth is added later by ticking **En el chat de la
  web** on its Discuss form. Publishing grants nothing: who may read and post
  is still decided by the channel's own `group_public_id`.

Worth checking at the same time:

- **The PWA.** The chat is a page of the app, so the website should also have
  `website_pwa`'s **Instalable como app** on. Without it the page still works,
  it simply is not part of an installable app.
- **Moderators.** `discuss_channel_zone` ships the four moderation rows with an
  empty moderator list. Until somebody is on it, held messages queue up with
  nobody to approve them and every visitor's first message sits in "en
  revisión" forever. Add them from **Discusión → Moderación**.
- **The wait the page promises.** The held card tells the author how long a
  review usually takes, and the number is read from
  `discuss_channel_moderation.late_alert_minutes` — the threshold at which that
  module emails the moderators about a message nobody has looked at. Move the
  threshold and the copy follows; there is nothing to edit here. If the
  parameter is missing or unreadable the page says 30 minutes.
- **Push notifications are not required.** The page works with them off, which
  is how it ships. Enabling them is `website_pwa_push`'s business and its
  switch; nothing on this page asks the visitor for permission.
