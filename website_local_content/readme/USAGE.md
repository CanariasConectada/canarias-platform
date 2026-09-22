1. Go to *Local Content > Configuration > Content Types*. Two types are
   seeded: *Living Memory* (`/explora/memoria-viva`) and *Places of
   Interest* (`/explora/lugares-de-interes`). Create a new record to add a
   new vertical: pick a unique URL slug and, optionally, restrict it to
   specific websites.
2. Define categories and subcategories per type under *Configuration >
   Categories*.
3. Create items under *Local Content > Items*, then *Approve* them: only
   approved and published items are visible on the website.
4. The public pages offer category browsing, free text search, sorting,
   a decade filter (for types with *Use Photo Year*) and an anonymous like
   button (one like per visitor cookie session, no login required).

Legacy URLs `/memoria-viva` and `/lugares-de-interes` are permanently
redirected (301) to the new `/explora/...` pages.

## Rating comments and moderation

Logged-in visitors rate an item (1-5 stars) with an optional comment from
the detail page. The stars are always published at once. When the comment
contains a word of the shared forbidden-word list (*Settings > Moderation
> Forbidden Words*, module `website_moderation_forbidden_word`) its text
is held: the author sees it with a "Your comment will be published after
review." notice, nobody else sees it, and the local content managers get
an email and a to-do activity.

Managers approve or reject held comments from *Local Content > Comments
pending review* (administrators: *Settings > Moderation > Local Content
Comments*). A rejected comment stays hidden; if its author writes a new
text it is evaluated again like any new comment.
