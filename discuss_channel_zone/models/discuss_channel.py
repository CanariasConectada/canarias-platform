# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models
from odoo.tools.translate import LazyTranslate

from odoo.addons.mail.tools.discuss import Store

_lt = LazyTranslate(__name__)

# The four channels this module seeds, with the English source of their name
# and description. Only the DISPLAY is translated: the stored columns stay
# plain ``varchar``/``text``, so renames, ``ilike`` search, mentions and every
# label built from ``channel.name`` keep working on one value.
#
# A translation is shown only while the stored text is still the seeded one
# (compared whitespace-insensitively): a channel an administrator renamed
# shows exactly what they typed, in every language.
SEEDED_CHANNEL_TEXTS = {
    "discuss_channel_zone.channel_canarias": (
        _lt("Canarias Conectada"),
        _lt(
            "Community channel of the whole platform. "
            "Open to everyone, visitors included."
        ),
    ),
    "discuss_channel_zone.channel_guanarteme": (
        _lt("Guanarteme"),
        _lt(
            "Neighbourhood channel of Guanarteme. An account is required to take part."
        ),
    ),
    "discuss_channel_zone.channel_tamaraceite": (
        _lt("Tamaraceite"),
        _lt(
            "Neighbourhood channel of Tamaraceite. An account is required to take part."
        ),
    ),
    "discuss_channel_zone.channel_lomolosfrailes": (
        _lt("Lomo los Frailes"),
        _lt(
            "Neighbourhood channel of Lomo los Frailes. "
            "An account is required to take part."
        ),
    ),
}

TRANSLATED_STORE_FIELDS = ("name", "description")


def _same_text(stored, source):
    return " ".join((stored or "").split()) == " ".join((source or "").split())


class DiscussChannel(models.Model):
    """Show the four seeded channels in the reader's language.

    Two places carry a channel's name to people: ``display_name`` (backend
    views, mail templates, many2one labels) and the Discuss store payload
    (``_to_store``: sidebar, header, mentions, bus updates). Both are
    rewritten here for the seeded channels only; every other channel, and
    every stored value, is untouched.
    """

    _inherit = "discuss.channel"

    def _seeded_channel_texts(self):
        """``{channel_id: (name_source, description_source)}`` of the seeded
        channels installed in this database."""
        texts = {}
        for xmlid, (name, description) in SEEDED_CHANNEL_TEXTS.items():
            channel = self.env.ref(xmlid, raise_if_not_found=False)
            if channel:
                texts[channel.id] = (name, description)
        return texts

    def _translated_seeded_value(self, field_name, texts=None):
        """The value of ``field_name`` to SHOW for ``self`` (one record)."""
        self.ensure_one()
        stored = self[field_name]
        texts = self._seeded_channel_texts() if texts is None else texts
        sources = texts.get(self.id)
        if not sources:
            return stored
        source = sources[TRANSLATED_STORE_FIELDS.index(field_name)]
        if not _same_text(stored, source._source):
            return stored
        return source._translate(self.env.lang or "en_US")

    @api.depends("channel_name_member_ids", "name")
    @api.depends_context("lang")
    def _compute_display_name(self):
        super()._compute_display_name()
        texts = self._seeded_channel_texts()
        for channel in self:
            if channel.id in texts:
                channel.display_name = channel._translated_seeded_value("name", texts)

    def _to_store(self, store: Store, fields, **kwargs):
        texts = self._seeded_channel_texts()
        if texts and self.ids and set(self.ids) & texts.keys():
            fields = [self._translate_store_field(field, texts) for field in fields]
        return super()._to_store(store, fields, **kwargs)

    def _translate_store_field(self, field, texts):
        """Swap a plain ``name``/``description`` store field for a computed one."""
        if isinstance(field, str):
            field_name, predicate = field, None
        elif type(field) is Store.Attr and field.value is None:
            field_name, predicate = field.field_name, field.predicate
        else:
            return field
        if field_name not in TRANSLATED_STORE_FIELDS:
            return field
        return Store.Attr(
            field_name,
            lambda channel: channel._translated_seeded_value(field_name, texts),
            predicate=predicate,
        )
