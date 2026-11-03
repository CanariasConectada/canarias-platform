Adds a "Instalaciones y servicios" filter to the business directory.

`company_facilities` turned what a shop offers from a paragraph of free text
into a shared catalogue with subdivisions and icons. The point of a catalogue
is that something can read it, and this is the something: the visitor picks
step-free access, card payment, parking nearby or "we speak English", and the
directory narrows to the shops that actually ticked them.

Two decisions worth knowing about:

* **Several ticks narrow, they do not widen.** Somebody asking for step-free
  access *and* parking wants both. One domain leaf per tick is what makes that
  true; a single `in` leaf holding every id would have meant "either".
* **The panel only offers what the current listing can actually return.** The
  chips are built from the same domain the listing uses, with the ticks taken
  back out, so a zone page never offers a filter that can only ever come back
  empty.

Every chip is a plain link built on the server, so the filter survives a shared
URL, a bookmark and a browser with JavaScript disabled, and each combination is
a real page.
