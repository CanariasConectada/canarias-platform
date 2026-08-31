# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Small text helpers shared by the queue and the sentences under it.

They live apart from both models on purpose: the job needs them to decide what
is worth sending to an engine, and the term needs them to decide where a
sentence sits in a page, so putting them in either one would make the two
models import each other.
"""

import bisect
import hashlib
import html
import re

# A snippet the website builder dropped on the page, or a heading. Both are
# read as "a new part of the page starts here", and the heading wins when the
# two coincide because "Quiénes Somos" tells a human far more than "Text -
# Image", which is what the builder calls that same block.
SECTION_MARKER = re.compile(
    r"""<(?:section|div|header|footer|main)\b[^>]*?"""
    r"""\bdata-name\s*=\s*["']([^"']+)["'][^>]*>"""
    r"""|<(h[1-6])\b[^>]*>(.*?)</\2\s*>""",
    re.IGNORECASE | re.DOTALL,
)

TAG = re.compile(r"<[^>]*>")

# Letters only: a digit is not something a translator can act on, and neither
# is punctuation. ``\w`` would accept both.
LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

# What a tag looks like once it is out of the way. Corner brackets rather than
# ``[0]`` because the pages already contain things like
# "[data_opcional_html_view_sostenible]" and a placeholder that can collide
# with real content is a placeholder that will eventually eat it.
PLACEHOLDER = "【%d】"
PLACEHOLDER_RE = re.compile(r"【(\d+)】")

# The whole tag, kept in the split so markup can be walked around rather than
# through. Same expression the glossary uses to fence terms.
MARKUP = re.compile(r"(<[^>]*>)")

# An HTML entity as it sits in a term, in either of the two spellings the
# website builder produces. The doubly-escaped form comes first and that
# ordering is load-bearing: the builder stores a typed non-breaking space as
# the text "&amp;nbsp;", and an alternation that tried the plain form first
# would match the leading "&amp;" -- a perfectly valid entity on its own --
# and leave a bare "nbsp;" behind as ordinary words. Shared with the glossary,
# which fences these off, and used here to keep them out of case changes:
# "&Aacute;" is a letter and "&aacute;" is a different letter, and "&NBSP;" is
# not an entity at all.
_ENTITY_NAME = r"(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]{1,31});"
ENTITY = re.compile(r"&amp;" + _ENTITY_NAME + r"|&" + _ENTITY_NAME)

# A word, for the purpose of deciding whether a term is shouting: any run of
# characters that carries at least one letter.
WORD = re.compile(r"\S*[^\W\d_]\S*", re.UNICODE)

# Below this many letters a single all-caps word is read as an acronym ("NIF",
# "TV", "IVA") and left alone. See :func:`is_shouting`.
SHOUT_MIN_LETTERS = 6

NBSP = " "
# The builder saves a typed hard space as the *text* "&nbsp;", which is stored
# escaped once more in ``arch_db``. Both spellings are seen in the wild.
NBSP_SOURCE = re.compile(r"&amp;nbsp;|&nbsp;", re.IGNORECASE)


def digest(value):
    """A stable identity for a piece of text, short enough to index."""
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def visible_text(term):
    """The term as a person reads it: no markup, no entities.

    Unescaped twice because the website builder stores a typed hard space as
    the literal text ``&amp;nbsp;`` -- one pass leaves ``&nbsp;``, which is
    still markup rather than a character.
    """
    return html.unescape(html.unescape(TAG.sub(" ", term or ""))).strip()


def term_has_words(term):
    """Whether there is anything here for a translator to translate.

    ``&amp;nbsp;`` on its own, or a lone ``<i class="fa fa-play"/>``, are terms
    as far as Odoo's extraction is concerned. Sending them to an engine spends
    a request on nothing and invites it to hand back something that is not the
    entity it was given -- which is precisely how ``&Nbsp;`` ended up rendered
    as five visible characters on the Italian pages on 2026-08-15.
    """
    return bool(LETTER.search(visible_text(term)))


# ----------------------------------------------------------------------
# Headings written in capitals
# ----------------------------------------------------------------------
def _content_pieces(text):
    """Yield ``(index, piece)`` for the parts of ``text`` that are not tags.

    :data:`MARKUP` keeps its separators, so the odd indices of the split are
    the tags and the even ones are what a visitor reads.
    """
    for index, piece in enumerate(MARKUP.split(text or "")):
        if index % 2 == 0 and piece:
            yield index, piece


def _map_letters(piece, transform):
    """Apply ``transform`` to ``piece`` everywhere except inside an entity."""
    out = []
    cursor = 0
    for found in ENTITY.finditer(piece):
        out.append(transform(piece[cursor : found.start()]))
        out.append(found.group(0))
        cursor = found.end()
    out.append(transform(piece[cursor:]))
    return "".join(out)


def is_shouting(text):
    """Whether ``text`` is written entirely in capitals.

    LibreTranslate falls apart on capitals: "CIENTOS DE COMERCIOS EN TU ZONA"
    came back as "_" in English and as "WISSENSCHAFTEN DES HANDELS" in German
    -- "CIENTOS" read as "ciencias" -- on eight production headings on
    2026-08-26. The model was trained on prose, and prose is not shouted.

    The rule, so that an acronym inside ordinary prose is never touched:

    * only what a visitor reads counts -- tags and entities are ignored;
    * every letter has to be upper case, and there has to be at least one;
    * a *single* word needs at least :data:`SHOUT_MIN_LETTERS` letters. "NIF",
      "TV" and "IVA" are acronyms and stay as they are; "DESCUBRE" is a word.
      Two or more words are always a heading, whatever their length: "EN TU
      ZONA" is nobody's acronym.

    A mixed-case sentence fails the second test on its first lower-case
    letter, so the acronyms it carries are never even looked at.
    """
    visible = " ".join(
        ENTITY.sub(" ", piece) for _index, piece in _content_pieces(text)
    )
    letters = LETTER.findall(visible)
    if not letters or any(letter.islower() for letter in letters):
        return False
    words = WORD.findall(visible)
    return len(words) >= 2 or len(letters) >= SHOUT_MIN_LETTERS


def whisper(text):
    """Turn a shouted term into sentence case, leaving markup and entities be.

    The first letter of the whole term is kept upper case, not the first of
    every piece: "CIENTOS DE <b>COMERCIOS</b>" is one sentence, and an engine
    given "Cientos de <b>Comercios</b>" would read a proper noun where there is
    none.
    """
    pieces = MARKUP.split(text or "")
    first = [True]

    def lower_then_cap(chunk):
        chunk = chunk.lower()
        if first[0]:
            found = LETTER.search(chunk)
            if found:
                first[0] = False
                chunk = (
                    chunk[: found.start()]
                    + found.group(0).upper()
                    + chunk[found.end() :]
                )
        return chunk

    for index, piece in _content_pieces(text):
        pieces[index] = _map_letters(piece, lower_then_cap)
    return "".join(pieces)


def shout(text):
    """Put a translation back into capitals, leaving markup and entities be."""
    pieces = MARKUP.split(text or "")
    for index, piece in _content_pieces(text):
        pieces[index] = _map_letters(piece, str.upper)
    return "".join(pieces)


# ----------------------------------------------------------------------
# Showing a sentence to a human without showing them the markup
# ----------------------------------------------------------------------
def mask(term):
    """Return ``term`` with every tag replaced by a numbered placeholder.

    Reported on 2026-08-16: "solo debes colocar los valores en los textos no en
    los div sections y data ni ninguna etiqueta html". A sentence in a page is
    rarely bare text -- half of them carry a ``<strong>`` around a brand or an
    icon before a call to action -- so hiding the markup is not a matter of
    trimming it away: whatever is shown has to be able to come back as the
    exact same markup, or correcting one word would strip the icons off the
    page.

    Numbering by position is what makes that reversible, and it is why the
    placeholders survive a human retyping the sentence around them while a
    stripped-and-guessed reconstruction could not.
    """
    if not term:
        return ""
    counter = [-1]

    def number(_found):
        counter[0] += 1
        return PLACEHOLDER % counter[0]

    return NBSP_SOURCE.sub(NBSP, TAG.sub(number, term))


def unmask(text, term):
    """Put ``term``'s markup back into a masked sentence a human edited.

    The tags come from the *source* term rather than from the translation:
    that is the one version nobody has retyped, so it is the only trustworthy
    account of what markup this sentence is supposed to carry. A placeholder
    the person deleted simply loses its tag rather than raising -- refusing the
    correction would be worse than losing a ``<strong>``.
    """
    tags = TAG.findall(term or "")

    def restore(found):
        position = int(found.group(1))
        return tags[position] if position < len(tags) else ""

    restored = PLACEHOLDER_RE.sub(restore, text or "")
    # Give the hard space back the spelling this very page uses, rather than a
    # bare character that would look identical here and different in the diff.
    spelling = NBSP_SOURCE.search(term or "")
    if spelling:
        restored = restored.replace(NBSP, spelling.group(0))
    return restored


def section_markers(value):
    """Where each part of a page begins, as ``(offset, label)`` in document order."""
    markers = []
    for found in SECTION_MARKER.finditer(value or ""):
        label = found.group(1) or visible_text(found.group(3))
        label = " ".join(label.split())[:120]
        if label:
            markers.append((found.start(), label))
    return markers


def section_at(markers, offset):
    """The label of the part of the page that ``offset`` falls inside."""
    if not markers or offset is None or offset < 0:
        return ""
    position = bisect.bisect_right([start for start, _ in markers], offset) - 1
    return markers[position][1] if position >= 0 else ""
