# Discuss Community

Phase 1 of moving the "Comunidad" experience into the Discuss backend:
community members (self-registered residents and walk-in guests) become
lightweight **internal** users whose whole backend is Discuss.

## The two doors

| Door | Route | Result |
| --- | --- | --- |
| Self-registration | `/web/signup` on any website | Internal + Community Member, zone of the arrival website |
| Walk-in guest | `POST /community/guest` | Internal community guest: signed reuse cookie, creation cap, daily GC |

`/community` is the public face: internal sessions are sent to `/odoo`,
portal sessions to the legacy `/chat`, anonymous visitors get the two
buttons on the platform's branded card.

## What a community member is

- `base.group_user` + `discuss_community.group_community_member` (the
  zone-channel read gate follows by implication) — never portal, never a
  merchant company on the user (always `base.main_company`).
- Backend stripped to the `mail.menu_root_discuss` subtree via an
  `ir.ui.menu._visible_menu_ids` override — no core menu is written to.
- `action_id = mail.action_discuss` (verified to exist before assignment),
  so login lands in Discuss.
- `chat_zone` = `website.company_id.commercial_zone` of the arrival site;
  `discuss_channel_zone` seats them in the general + neighbourhood channel.
- Kept out of `mail.channel_all_employees` (and any other group
  auto-subscribed channel) by a carve-out in
  `_subscribe_users_automatically_get_members`.

Merchants keep their company-derived zone; backend-invited users stay
portal; backend-created users are untouched.

See `readme/DESCRIPTION.md` for the security audit notes behind making
residents internal, and the tests for the exact contracts.
