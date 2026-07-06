* Optional "open now / closed" badge computed client-side from the parsed
  opening hours (the legacy module shipped a hand-rolled inline script;
  a clean frontend asset should replace it).
* Optional bridge with `website_directory` overriding
  `res.company._get_directory_sync_fields()` so microsite edits refresh
  the directory entry (the base URL priority already covers
  `website_id.domain`).
* Image size variants (`image_512` …) for the hero/banner images to avoid
  serving full-size uploads.
