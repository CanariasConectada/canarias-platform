From any QWeb template:

```xml
<t t-call="website_map_embed.map_iframe">
    <t t-set="map_url" t-value="partner._canarias_map_embed_url()"/>
    <t t-set="map_title" t-value="partner.display_name"/>
</t>
```

Nothing is rendered when `map_url` is empty.
