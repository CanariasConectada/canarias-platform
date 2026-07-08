* The sidebar filter is single-select (one seal at a time). Multi-seal
  filtering would require the directory to accept repeated query parameters.
* Badge colours are hard-coded per level (bronze/silver/gold). A colour
  configurable per `certification.type` could replace the mapping.
* Seal validity is evaluated at request time against `expiry_date`; there is
  no caching, so very large directories may want a stored "has valid seal"
  helper on the company for indexing.
