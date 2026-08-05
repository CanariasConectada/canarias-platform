Seeds the community chat of Canarias Conectada and keeps membership of it in
sync with each user's commercial zone.

Four channels:

- **Canarias Conectada** — the general channel. Readable and postable by
  **everyone**, anonymous visitors included.
- **Guanarteme**, **Tamaraceite**, **Lomo los Frailes** — the neighbourhood
  channels. **Closed to visitors**: an account is required to enter. Both
  merchants and ordinary residents belong to them.

Nobody joins or leaves by hand. Membership is a function of the account: a
merchant's zone comes from their company, a resident with no business picks
their own, and everybody is in the general channel. The projection of that
function onto `discuss.channel.member` is idempotent and runs on create, on
the writes that can change the answer, and nightly.
