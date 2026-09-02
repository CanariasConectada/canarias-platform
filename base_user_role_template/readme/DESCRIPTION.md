`base_user_role` re-derives a user's groups from their roles on **every**
`res.users.write`: whatever an administrator granted by hand on the Access
Rights tab is silently reverted moments later, which is what the "changes
made here will not be persistent" banner warns about.

This module turns the role into a **template**. The sync only ever *adds*
the groups the enabled roles imply:

- Assigning a role still applies everything it carries, immediately.
- A group granted by hand to one particular user now **survives**.
- A role-implied group removed by hand is healed back on the next sync:
  the role remains the guaranteed minimum.
- Removing a role line still resets the user to the remaining roles'
  template, exactly as before -- that is the one moment the full
  replacement still runs.

The banner is retired: with this module installed, what it warned about no
longer happens.
