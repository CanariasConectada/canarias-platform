## Where a user's zone comes from

`res.users._get_chat_zone()` answers it, in this order:

1. **The company**, when the account has a *usable* one — active, and not the
   platform's own company (`base.main_company`). That is the rule documented on
   `res.company._get_own_company_for_directory()`.
2. **`res.users.chat_zone`**, the manual field a resident sets on their own
   profile (Preferences → Chat Zone). It is a fallback, never an override.
3. **The general zone** for everyone else — platform staff, and residents who
   never picked.

A public (anonymous) user has no zone: the method returns `False`.

## Moving a business

Change **Commercial Zone** on the company form. Every user of that company is
moved to the new neighbourhood channel and out of the old one, silently: no
"joined"/"left" notice is posted, because none is posted on channels of type
`channel`.

## Reconciliation

`Discuss Channel Zone: reconcile channel membership` runs nightly, in batches
of 500 users, and logs the drift it corrected:

```
discuss_channel_zone: reconciled 812 users, drift 3 added / 1 removed
```

A healthy platform prints zeros. Run it by hand from **Settings → Technical →
Scheduled Actions** after a data migration, or call
`env["res.users"]._cron_sync_zone_channels()`.

Archived users are skipped: their existing membership is left alone and they
are never re-seated.
