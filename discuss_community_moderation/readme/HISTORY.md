## 19.0.1.0.1 (2026-09-30)

- The member branch (trust threshold) now follows
  `res.users.is_community_member` from `discuss_community` 19.0.1.8.0:
  administrators, merchants and zone managers who also hold the community
  group are no longer moderated as residents. Guests are still always held.
  Falls back to the plain community group check when the field is absent.
