## 19.0.1.0.0 (2026-07-06)

- Initial version. Replaces the legacy production core patch on
  `web/controllers/home.py` (`_login_redirect` company cookie logic) with
  an installable addon, dropping the `[LOGIN-DEBUG]` logging and adding
  guards for websiteless contexts.
