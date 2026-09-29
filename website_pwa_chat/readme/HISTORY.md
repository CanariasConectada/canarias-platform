## 19.0.6.6.0 (2026-09-25)

- Support window simplified after client feedback ("huge, long, jumps
  around; support mixed with messages to publish"). The support page reused
  the community-channel template and carried its publishing pieces: the
  visitor hint "someone on the team reads your message before publishing
  it", the "held for review" zone, and an identify card whose footer sold an
  account with "your messages are published instantly, no review". All of
  them are gone from support; community channel pages keep them.
- Inside the window: no title (the window header says Soporte), messages
  that scroll, and one composer row ("Write your question…", bell, Send)
  pinned at the bottom. The site's cookie bar and the backend shortcut no
  longer render inside the frame.
- The window sits above the site's cookie bar (z-index 1056, was 1030): the
  bar is a Bootstrap modal (1055) pinned to the bottom and covered the
  composer, on a phone the whole bottom third of the window, until the
  visitor answered it. The floating button stays at 1030.
- The identify card became one optional line (name, optional email, Save),
  shown only to anonymous visitors and only after their first message. It
  saves in place through the new `/website_pwa_chat/support/identify` route
  instead of reloading the window; `/chat/soporte/identificarme` stays as
  the no-script fallback. Fixed on the way: the page's submit listener
  caught the identify form's submit too and sent the composer instead.
- Logged-in users, walk-in community guests included, are no longer asked
  for a name on the website (reverts that part of 19.0.6.4.0); they give it
  in the Discuss dialog, which is unchanged.
- Kept: the 26rem x 42rem window, the Discuss "Request support" button and
  its name dialog, conversations named after the requester, the chime.
- Tours: window size unchanged; new tours check, as an anonymous visitor
  and as a logged-in guest, on desktop and phone, that the window shows no
  review/publish/signup/channel UI, that the first message appears at once,
  and that nothing but the conversation scrolls after it.

## 19.0.6.5.0 (2026-09-26)

- Foreground chime when somebody else's message arrives in the open chat
  (bus), unless the visitor is looking at it (page visible and focused; the
  floating window counts as not looking while the shop around it has the
  focus). Throttled and muted through `mail_push_guest`'s shared chime, now
  a dependency. Deploy note: `mail_push_guest` is already installed in
  production, so `-u website_pwa_chat` needs nothing else; a database
  without it installs it on the update.
- Message-sound switch (bell) next to the chat title; it stores the same
  preference as the backend's Discuss "message sound".

## 19.0.6.4.1 (2026-09-26)

- i18n: `es.po` held only the Discuss dialog strings, so the website support
  bubble showed the English of `en.po` ("Close the chat", "Talk to support")
  to Spanish readers, and the dialog's "Cancel" had no entry. All .po files
  regenerated from a fresh export against the source terms; de, fr, it, pl
  and pt gain the missing user-facing strings. The migration reloads es_ES
  with overwrite, because a regular update keeps the stale English value as
  an "existing translation".

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
