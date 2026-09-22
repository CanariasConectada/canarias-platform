One administrator-managed list of forbidden words and expressions, shared
by every moderated text of the platform (merchant reviews, local content
comments...).

The module is deliberately small: a `moderation.forbidden.word` model, a
menu under *Settings > Moderation*, a seeded Spanish list and two matcher
helpers that consuming modules call:

- `_find_matches(text)` returns the entries found in a text;
- `_contains_forbidden(text)` is the boolean shortcut.

Matching rules (the same normalization is applied to the list and to the
text, so one spelling per word is enough):

- case and accents are ignored: `IMBÉCIL`, `imbecil` and `Imbécil` are the
  same word; the enye is kept as a letter of its own (`coño` never becomes
  `cono`);
- only whole words hit: `imbécil` flags `imbécil!` but not `imbecilidad`;
- entries may be whole expressions (`hijo de puta`, `que te den`);
- repeated letters or symbol substitutions (`imbeeecil`, `imb3cil`) are not
  tolerated, on purpose: a predictable rule is one moderators can reason
  about.

Uniqueness is enforced on the normalized form, so `cabron` and `cabrón`
cannot both be listed.
