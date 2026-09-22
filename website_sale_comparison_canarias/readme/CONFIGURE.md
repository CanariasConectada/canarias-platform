The comparator ships **switched off**. To offer it to visitors:

1. Go to *Website > Configuration > Settings*, block **Price comparator**.
2. Tick **Price Comparator** and save.

The switch is platform-wide (one setting for every website) and takes effect
on the next page load: no restart, no module update. It is stored in the
system parameter `website_sale_comparison_canarias.enabled` (`True` /
`False`), which can also be set from *Settings > Technical > System
Parameters*.

With the switch off nothing is rendered: no Compare button on the cards, no
Compare prices button or picker on the product page, no comparison bar, and
`/shop/compare` sends the visitor to the shop. The picker's data endpoint
(`/shop/compare/candidates`) answers with an empty list. All data and views
stay installed, so switching back on restores everything as it was.
