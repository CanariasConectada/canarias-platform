Phase 1 of moving the Canarias Conectada "Comunidad" experience into the
Discuss backend.

Two doors, one account shape
----------------------------

- **Signup on any of the platform's websites** (`/web/signup`): the new
  resident becomes an **internal** user carrying the *Community Member* group
  instead of the portal default. Only uninvited, website-served signups are
  promoted — a user invited from the backend stays portal, and users created
  any other way (backend, XML-RPC, shell) are untouched.
- **"Enter as guest"** (`POST /community/guest`): one click mints a
  lightweight internal community guest, mirroring
  `website_login_branding`'s portal guests guard for guard — non-routable
  login domain, signed HMAC reuse cookie, rolling-window creation cap,
  suppressed security-update mails, and a daily garbage collector that
  purges idle guests unless they posted a message.

Either way the account holds exactly `base.group_user` +
`group_community_member` (the zone-channel read gate arrives by
implication), lives in the platform company only, and:

- **sees a backend that is Discuss and nothing else** — the visible-menu set
  is filtered at its single choke point (`ir.ui.menu._visible_menu_ids`) down
  to the `mail.menu_root_discuss` subtree, so no core menu is written to and
  new apps are stripped automatically;
- **lands in Discuss after login** — `action_id` is set to the (verified
  existing) `mail.action_discuss` client action;
- **starts in the right channel** — the website of arrival decides:
  `website.company_id.commercial_zone` is stored in `chat_zone` and
  `discuss_channel_zone` seats the account in the general channel plus the
  neighbourhood one. Merchants keep their company-derived zone untouched.

The `/community` page routes by identity: internal sessions go to `/odoo`,
portal sessions keep the legacy `/chat`, and anonymous visitors get the two
doors on the platform's branded card.

Security posture of internal community members
----------------------------------------------

Making residents internal opens `base.group_user`'s ACLs to them; the Phase 1
audit and its mitigations:

- **Staff channels**: `mail.channel_all_employees` auto-seats every internal
  user; a carve-out in `_subscribe_users_automatically_get_members` keeps
  community members out of group-auto-subscribed channels (unless a channel
  is explicitly gated on the community group).
- **Contacts**: `res.partner` visibility is already narrowed platform-wide by
  `partner_multi_company_restrict`'s global rules.
- **Sales**: plain employees hold **no** ACL on `sale.order` / order lines —
  a community member cannot read any order (tested).
- **Companies**: employee ACL on `res.company` is read-only; create/write
  raise (tested), and read is scoped by core's record rules.
- **Self-service escalation**: `group_ids` is not self-writeable; a member
  cannot grant themselves groups (tested).

No extra `ir.rule` narrowing ships in Phase 1 because no concrete leak
survived the audit; moderation of community guests and members is Phase 2
(the existing `discuss_channel_moderation` "guest" semantics cover anonymous
`mail.guest` sessions, not logged-in accounts, so covering these users there
was not a trivial extension).
