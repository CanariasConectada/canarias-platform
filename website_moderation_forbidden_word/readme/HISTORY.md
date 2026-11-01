# 19.0.1.0.0 (2026-09-22)

First version. Replaces the `review.forbidden.word` list of
`partner_reviews` (migrated automatically) and gives `website_local_content`
its comment moderation list. Seeded with the two legacy production lists
merged plus a categorized Spanish extension (344 entries, 9 of them shipped
archived because of their frequent legitimate use: basura, paja, timo,
racista, tonto, boludo, boluda, verga, tetas). Entries need at
least one letter or digit; plural and inflected forms are separate entries
(no stemming).
