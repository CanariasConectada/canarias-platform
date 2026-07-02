Hierarchical business categories (`business.category`) to segment companies
of the Canarias Conectada marketplace.

Categories form an unlimited tree (in practice 3 levels are used: root
category, subcategory, specialty) and are assigned to companies through the
`business_category_ids` many2many field, used as filter by the public
directory (`website_directory`).

On installation the module seeds the default Canarias Conectada taxonomy
(~130 categories) **without** external identifiers: the user fully owns the
records afterwards and module updates never recreate or overwrite them.
