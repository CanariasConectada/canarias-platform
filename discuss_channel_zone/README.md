# Discuss Channel Zone

Seeds the community chat of Canarias Conectada and keeps membership of it in
sync with each user's commercial zone.

## The four channels

| Channel | xmlid | Who can read and post |
| --- | --- | --- |
| Canarias Conectada | `channel_canarias` | **Everyone**, anonymous visitors included |
| Guanarteme | `channel_guanarteme` | Registered users only (portal or internal) |
| Tamaraceite | `channel_tamaraceite` | Registered users only (portal or internal) |
| Lomo los Frailes | `channel_lomolosfrailes` | Registered users only (portal or internal) |

All four are pre-moderated for guests through `discuss_channel_moderation`.

## How the gate works

`ir_rule_discuss_channel_all` (`mail/security/mail_security.xml`) opens a
channel of type `channel` to a session when

```
group_public_id = False   OR   group_public_id IN user.all_group_ids
```

- The **general** channel therefore passes `group_public_id = False`
  *explicitly*. Leaving the field empty does **not** mean "open": the stored
  compute `_compute_group_public_id` fills it with `base.group_user` for any
  channel, which would close it to visitors and residents alike.
- The **zone** channels are gated on `group_zone_channel_member`, a group of
  this module that `base.group_user` and `base.group_portal` both imply
  (`implied_by_ids`) and `base.group_public` does not. A guest session runs as
  `base.public_user`, whose only group is `base.group_public`, so the zone
  channels are filtered out of every anonymous `search()` — the public routes
  answer 404.

Membership plays no part in that rule: it only decides whose Discuss sidebar
the channel shows up in. Guests are never made members of anything.

## Where a user's zone comes from

`res.users._get_chat_zone()`, in strict order:

1. the user's **company**, when it is *usable* — active and not
   `base.main_company` (the rule documented on
   `res.company._get_own_company_for_directory`);
2. `res.users.chat_zone`, the field a resident sets on their own profile;
3. the general zone, for everyone else.

A public user has no zone at all.

## Keeping it in sync

`res.users._sync_zone_channels()` projects that function onto
`discuss.channel.member`. It is idempotent — it diffs against the memberships
that exist and returns the drift it corrected — which is why the same method
runs from every trigger:

- `res.users.create`;
- `res.users.write`, when `company_id` or `chat_zone` changes;
- `res.company.write`, when `commercial_zone` changes (every user of the
  company moves);
- the nightly cron, in batches of 500, logging the drift;
- `post_init_hook`, for the accounts that predate the install.

Joining and leaving are silent: core posts no notice on channels of type
`channel`.
