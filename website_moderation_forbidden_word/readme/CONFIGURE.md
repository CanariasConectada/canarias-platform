The list is maintained from *Settings > Moderation > Forbidden Words*
(system administrators). Consuming modules may open the same list from
their own menus for their managers (e.g. *Reviews > Forbidden Words* for
review administrators): the *Settings* root is only visible to
administrators.

The list is editable inline, importable (*Favorites > Import records*) and
archivable: archive a word instead of deleting it to keep the history.
The optional *Note* column documents why an entry is listed or which false
positives to watch for.

The initial seed (344 entries) merges the two legacy production lists
(living memory and merchant reviews, 52 entries) with an extension grouped
by category in `data/forbidden_words.xml`: insults (Spain and Latin
American variants), profanity and explicit sexual content, hate speech,
threats, spam and scams. It is loaded once (`noupdate`): later edits are
never overwritten by a module update.
