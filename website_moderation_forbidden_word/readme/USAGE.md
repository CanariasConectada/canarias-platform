From another module, always call the matcher through `sudo()` because the
list is readable by administrators only:

```python
words = self.env["moderation.forbidden.word"].sudo()
if words._contains_forbidden(record.comment):
    record.moderation_status = "pending"
hits = words._find_matches(record.comment)  # ["hijo de puta", "timo"]
```

Never show the visitor which word matched: a neutral "will be published
after review" notice is enough and gives no hint to work around the list.
