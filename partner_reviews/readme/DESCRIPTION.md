Customer reviews for merchant websites, rebuilt on top of Odoo's native
`rating.rating` model.

Each merchant of the platform is a company with its own website. When the
*Enable Reviews Page* flag is set on a company, its website gets a public
`/resenas` page where customers can:

- rate the business from 1 to 5 stars (one review per customer),
- leave an optional text comment,
- edit or delete their own review at any time.

Reviews are plain `rating.rating` records (stars in `rating`, comment in
`feedback`, merchant answer in the native `publisher_comment` from
`portal_rating`). This module only adds:

- a moderation state machine (`pending` / `approved` / `rejected`) with a
  configurable forbidden words list that holds suspicious reviews for a
  manual check,
- email and to-do notifications to moderators and merchants,
- backend views, menus and security groups scoped per company,
- the public website page, rendered fully server-side (no JavaScript).
