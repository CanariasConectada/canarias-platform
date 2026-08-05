- **No frontend zone picker yet.** A resident sets `chat_zone` from the backend
  preferences form. Portal users have no backend, so today somebody with access
  has to set it for them, or the resident stays in the general channel only. A
  small portal form is the missing piece.
- **The cron does not commit between batches.** Batching at 500 bounds the work
  per slice but the whole reconciliation is one transaction. That is fine at the
  current size (hundreds of accounts); a platform with tens of thousands should
  commit per batch.
- **Archived users keep their seats.** Deactivating an account leaves its
  memberships in place, deliberately (history is not ours to rewrite), so an
  archived user still counts towards `member_count`. Purging them would be a
  separate, explicit action.
- **A zone with no channel is silently skipped.** `ZONE_SELECTION` and the
  channel data are two lists; adding a zone to the selection without adding its
  channel leaves those users in the general channel only, with no warning.
