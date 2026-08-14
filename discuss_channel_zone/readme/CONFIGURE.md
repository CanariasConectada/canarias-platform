Nothing has to be configured for the module to work: installing it seeds the
four channels, their moderation rows and the nightly cron, and seats every
existing account.

Two things are worth setting afterwards:

- **Moderators.** The four `discuss.channel.moderation` rows ship with an empty
  moderator list, so held messages queue up with nobody to approve them. Add
  moderators from **Discuss → Moderation**.
- **Portal moderation.** Only guests are held by default. Turn on **Moderate
  Portal Users** on a channel if a neighbourhood needs its residents held too.

The `Community Chat: Registered Member` group is granted automatically to every
portal and internal user; it is not meant to be assigned by hand.
