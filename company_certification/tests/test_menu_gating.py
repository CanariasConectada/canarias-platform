# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Visibility is gated by each vertical's user group.

A plain internal user (no vertical group) must not see the vertical's root
menu, its questionnaire or its evaluations. A user in the group sees only
their own vertical.
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import NO_MAIL_CTX, CertificationCase


@tagged("post_install", "-at_install")
class TestMenuGating(CertificationCase):
    def _visible_menus(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def test_menu_hidden_for_plain_internal_user(self):
        self.assertNotIn(
            self.cert_type.menu_id.id, self._visible_menus(self.plain_user)
        )

    def test_menu_visible_for_group_member(self):
        self.assertIn(self.cert_type.menu_id.id, self._visible_menus(self.user))

    def test_seeded_verticals_hidden_for_plain_internal_user(self):
        visible = self._visible_menus(self.plain_user)
        for xmlid in (
            "company_certification.certification_type_silver",
            "company_certification.certification_type_sustainability",
        ):
            cert_type = self.env.ref(xmlid)
            self.assertNotIn(cert_type.menu_id.id, visible)

    def test_config_menu_hidden_for_plain_internal_user(self):
        menu = self.env.ref("company_certification.menu_certification_root")
        self.assertNotIn(menu.id, self._visible_menus(self.plain_user))
        self.assertIn(menu.id, self._visible_menus(self.manager))

    def test_survey_read_gated_by_group(self):
        with self.assertRaises(AccessError):
            self.survey.with_user(self.plain_user).read(["title"])
        self.assertTrue(self.survey.with_user(self.user).read(["title"]))

    def test_survey_of_other_vertical_not_readable(self):
        """Group members only read the questionnaires of their vertical."""
        silver_survey = self.env.ref("company_certification.survey_silver_economy")
        with self.assertRaises(AccessError):
            silver_survey.with_user(self.user).read(["title"])

    def test_menu_branch_follows_type_active_state(self):
        """Archiving a vertical takes its whole entry point with it.

        The children matter as much as the root: a child left archived under
        a live root gives a menu that opens onto nothing.
        """
        branch = self.cert_type._menu_branch()
        self.assertTrue(len(branch) > 1, "the generated menu has children")
        self.cert_type.active = False
        self.assertFalse(
            any(branch.exists().with_context(active_test=False).mapped("active"))
        )
        self.cert_type.active = True
        self.assertTrue(
            all(branch.exists().with_context(active_test=False).mapped("active"))
        )

    def test_generated_menu_children_carry_every_language(self):
        """The generated labels exist in each installed language, not just one.

        These rows are written by code through ``_()``, so they are invisible
        to a ``.po`` import: whichever language the install ran in is the only
        one they would ever carry. The regression this guards is a Spanish
        backend showing "My Evaluations" while the translation sits unused in
        ``i18n/es.po``.
        """
        for code in ("en_US", "es_ES"):
            self.env["res.lang"]._activate_lang(code)
        # ``get_installed`` is ormcached and the activations above changed it.
        self.env.registry.clear_cache()

        self.cert_type._sync_menu_child_names()
        children = self.cert_type._menu_branch() - self.cert_type.menu_id
        self.assertTrue(children, "the generated menu has children")

        # Asserted as literal strings rather than "the two languages differ":
        # on a database installed in Spanish the source key holds Spanish too,
        # so a difference test passes while proving nothing. These are the
        # exact msgstr values in i18n/es.po, which is what has to arrive.
        self.assertEqual(
            sorted(children.with_context(lang="en_US").mapped("name")),
            ["My Evaluations", "New Evaluation"],
        )
        self.assertEqual(
            sorted(children.with_context(lang="es_ES").mapped("name")),
            ["Mis evaluaciones", "Nueva evaluación"],
        )

    def test_user_input_isolated_by_company_and_vertical(self):
        answer = self._run_evaluation(3)
        # The evaluating user sees their company's evaluation.
        self.assertIn(
            answer.id,
            self.env["survey.user_input"]
            .with_user(self.user)
            .search([("certification_type_id", "=", self.cert_type.id)])
            .ids,
        )
        # A group member of another company sees nothing.
        other_company = self.env["res.company"].create({"name": "Other Shop"})
        other_user = new_test_user(
            self.env,
            login="cert_other",
            groups="base.group_user",
            company_id=other_company.id,
            company_ids=[(6, 0, other_company.ids)],
            context=NO_MAIL_CTX,
        )
        other_user.write({"group_ids": [(4, self.group_user.id)]})
        self.assertFalse(
            self.env["survey.user_input"]
            .with_user(other_user)
            .search([("certification_type_id", "=", self.cert_type.id)])
        )
        # A plain internal user cannot read it at all.
        with self.assertRaises(AccessError):
            answer.with_user(self.plain_user).read(["state"])

    def test_user_input_lines_isolated_by_company(self):
        """The answers themselves, not just the evaluation that holds them.

        survey.user_input.line has no company_id of its own, so it is only
        covered if the rule reaches through user_input_id -- and the group
        implies no survey group, so a missing rule means no domain at all
        rather than a restrictive default.
        """
        answer = self._run_evaluation(3)
        line_model = self.env["survey.user_input.line"]
        # Positive control: the evaluating user still reads their own answers.
        self.assertTrue(
            line_model.with_user(self.user).search([("user_input_id", "=", answer.id)])
        )
        other_company = self.env["res.company"].create({"name": "Other Shop Lines"})
        other_user = new_test_user(
            self.env,
            login="cert_other_lines",
            groups="base.group_user",
            company_id=other_company.id,
            company_ids=[(6, 0, other_company.ids)],
            context=NO_MAIL_CTX,
        )
        other_user.write({"group_ids": [(4, self.group_user.id)]})
        # Searched by survey rather than by parent: the parent is already
        # unreadable, so this is the query that leaks if the rule is absent.
        self.assertFalse(
            line_model.with_user(other_user).search(
                [("survey_id", "=", self.survey.id)]
            )
        )

    def test_manager_sees_all_evaluations_of_managed_vertical(self):
        answer = self._run_evaluation(3)
        found = (
            self.env["survey.user_input"]
            .with_user(self.manager)
            .search([("certification_type_id", "=", self.cert_type.id)])
        )
        self.assertIn(answer.id, found.ids)
