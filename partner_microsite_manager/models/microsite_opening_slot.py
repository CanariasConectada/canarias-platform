# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..tools.opening_hours import find_slot_problem, float_to_hhmm

# Keys follow ``date.weekday()`` (Monday = 0), the index the parser, the
# template rows and the browser widget already agree on.
WEEKDAY_SELECTION = [
    ("0", "Monday"),
    ("1", "Tuesday"),
    ("2", "Wednesday"),
    ("3", "Thursday"),
    ("4", "Friday"),
    ("5", "Saturday"),
    ("6", "Sunday"),
]


def slot_problem_message(env, weekday_field, problem):
    """Translate a :func:`find_slot_problem` result into a sentence.

    Shared by the stored slots and the editor's transient rows so the
    merchant reads the same complaint wherever the check fires.
    """
    labels = dict(weekday_field._description_selection(env))
    if problem[0] == "order":
        day, open_time, close_time = problem[1]
        return _(
            "%(day)s: the shop cannot close (%(close)s) before it opens "
            "(%(open)s). Times must stay within one day, opening first.",
            day=labels[str(day)],
            open=float_to_hhmm(open_time),
            close=float_to_hhmm(close_time),
        )
    (day, open_a, close_a), (_day, open_b, close_b) = problem[1], problem[2]
    return _(
        "%(day)s: %(first)s and %(second)s overlap. Each period of the day "
        "must end before the next one starts.",
        day=labels[str(day)],
        first=f"{float_to_hhmm(open_a)}-{float_to_hhmm(close_a)}",
        second=f"{float_to_hhmm(open_b)}-{float_to_hhmm(close_b)}",
    )


class MicrositeOpeningSlot(models.Model):
    """One opening period of a shop: a weekday, an opening and a closing time.

    The source of truth for a shop's schedule since 19.0.2.8.0.
    ``res.company.microsite_opening_hours`` (the compact text every public
    template reads) is generated from these rows, so nothing downstream had
    to learn a new format.
    """

    _name = "microsite.opening.slot"
    _description = "Microsite Opening Slot"
    _order = "company_id, weekday, open_time"

    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        ondelete="cascade",
        index=True,
    )
    weekday = fields.Selection(WEEKDAY_SELECTION, required=True)
    open_time = fields.Float(string="Opens", required=True)
    close_time = fields.Float(string="Closes", required=True)

    def unlink(self):
        """A company left without rows shows no hours.

        The generated text is a stored compute that keeps its value when
        the company has no rows (so the legacy free text of an unconverted
        shop survives). Deleting the LAST row is the one case where "no
        rows" means "no hours", and it has to hold whichever screen did the
        deleting: the content editor (which replaces all rows on save) and
        the company form (where an administrator removes rows one by one)
        both end up here. A shop whose text never became rows is never
        touched, because it never has rows to delete.
        """
        companies = self.company_id
        result = super().unlink()
        for company in companies:
            if not company.microsite_opening_slot_ids:
                company.microsite_opening_hours = False
        return result

    @api.constrains("company_id", "weekday", "open_time", "close_time")
    def _check_slots(self):
        for company in self.company_id:
            slots = company.microsite_opening_slot_ids
            problem = find_slot_problem(
                (slot.weekday, slot.open_time, slot.close_time) for slot in slots
            )
            if problem:
                raise ValidationError(
                    slot_problem_message(self.env, self._fields["weekday"], problem)
                )
