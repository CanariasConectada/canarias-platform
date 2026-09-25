## 19.0.6.4.0 (2026-09-25)

- **Request support** from the backend Discuss sidebar, for every internal
  user who is not a support agent (merchants, walk-in community guests). It
  opens or reopens the same partner-keyed conversation the website button
  opens, through the new `/website_pwa_chat/support/request` route. Agents
  and administrators neither see it (`session_info`) nor may call it.
  Walk-in community guests are first asked their name (required) and an
  optional email in a small dialog; the answer is stored through
  `_support_identify`, exactly like the website identify card.
- Support conversations are named after who is asking (`Soporte · <name>`,
  at most 64 characters): the name typed on the identify card, else the
  account, else the guest. Community guests (`Invitado …`) are now offered
  the identify card. A migration renames the existing conversations. The
  rename writes every installed language when `discuss.channel.name` is
  translatable, and a plain value when it is not.
- The floating support window is larger: 26rem x 42rem on desktop, growing
  upwards, and nearly full-screen below 576px. The page inside it fills the
  frame and only the conversation scrolls. The identify card is more compact
  in the frame.
- New `i18n/es.po` for the strings written in English. The new strings are
  also translated in de, en, fr, it, pl and pt.

## 19.0.6.3.1 (2026-09-09)

- Support agents are appointed by ticking **Soporte: atender a los
  visitantes** on the user form. `base_user_role` was retired from the
  platform, so the role `canarias_mig.role_support` no longer exists; the
  tests grant the group directly too.

## 19.0.2.0.0 (2026-08-14)

- A private line to support, above the channel list: one conversation per
  visitor, account or guest, kept private by `channel_type = "group"` so only
  its members can read it. Answered by administrators or by anybody holding
  the new **Soporte: atender a los visitantes** group, seated when a
  conversation opens and again by a nightly cron so appointing an agent is
  enough to start answering the ones already waiting. On this platform the
  group is granted through the role `canarias_mig.role_support`; see
  CONFIGURE.

## 19.0.1.0.0 (2026-08-05)

- First release: `/chat` and `/chat/<id>` rendered inside `website.layout`, the
  per-website `chat_enabled` switch, the per-channel `website_chat_published`
  opt-in seeded on the four community channels, a self-contained frontend chat
  built on `bus` (no `im_livechat` dependency), the "en revisión" state
  rendered for its author only, live updates for new, approved and rejected
  messages, and a "Comunidad" menu entry served on the host portal as a path
  and on the websites that only link to it as an absolute URL.
