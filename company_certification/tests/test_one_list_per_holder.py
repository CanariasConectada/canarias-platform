# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from .common import CertificationCase

# The domain of `action_all_certification_evaluations`, restated here rather
# than read from the action: what this suite guards is that the LIST a holder
# opens shows every seal they hold, and a test that borrowed the action's own
# domain would keep passing if that domain were narrowed back to one seal.
LIST_DOMAIN = [("certification_type_id", "!=", False), ("test_entry", "=", False)]


@tagged("post_install", "-at_install")
class TestOneListPerHolder(CertificationCase):
    """One list for every seal, and only the rows that belong to the reader.

    Asked for on 2026-08-14: the two seals were listed one menu each, and they
    should read like `website_local_content` reads memoria viva and lugares de
    interés — a single list with the vertical as a grouping.

    Whether that list is honest is not a question about menus, so none of this
    goes through one. It is `survey_user_input_rule_certification_user` doing
    the work: "a seal whose user group I hold, in a company I belong to".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # A second vertical, so "one list" has something to put in it. Built
        # the way the engine documents a vertical: two groups, a survey and a
        # certification.type record.
        cls.other_group_user = cls.env["res.groups"].create(
            {
                "name": "Test Other Seal User",
                "implied_ids": [
                    (
                        4,
                        cls.env.ref(
                            "company_certification.group_certification_user"
                        ).id,
                    )
                ],
            }
        )
        cls.other_survey = cls.env["survey.survey"].create(
            {
                "title": "Test Other Seal Survey",
                "survey_type": "survey",
                "scoring_type": "scoring_without_answers",
                "access_mode": "public",
                "users_login_required": True,
            }
        )
        cls.other_type = cls.env["certification.type"].create(
            {
                "name": "Test Other Seal",
                "code": "test_other_seal",
                "survey_id": cls.other_survey.id,
                "group_user_id": cls.other_group_user.id,
            }
        )

        cls.holder_company = cls.env["res.company"].create({"name": "Holder Shop"})
        cls.other_company = cls.env["res.company"].create({"name": "Somebody Else"})

        cls.holder = cls.env["res.users"].create(
            {
                "name": "Seal Holder",
                "login": "cert_seal_holder",
                "company_id": cls.holder_company.id,
                "company_ids": [(6, 0, cls.holder_company.ids)],
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.group_user.id,
                            cls.other_group_user.id,
                        ],
                    )
                ],
            }
        )

    def _evaluation(self, survey, company):
        return self.env["survey.user_input"].create(
            {"survey_id": survey.id, "company_id": company.id, "test_entry": False}
        )

    def _listed_by_holder(self):
        return self.env["survey.user_input"].with_user(self.holder).search(LIST_DOMAIN)

    def test_both_seals_come_back_in_the_same_list(self):
        """The whole request, in one assertion.

        Before this, each seal was only reachable through its own module's
        rule and its own menu, so no single search could return both.
        """
        mine_first = self._evaluation(self.survey, self.holder_company)
        mine_second = self._evaluation(self.other_survey, self.holder_company)

        listed = self._listed_by_holder()

        self.assertIn(mine_first, listed)
        self.assertIn(mine_second, listed)
        self.assertEqual(
            listed.certification_type_id,
            mine_first.certification_type_id | mine_second.certification_type_id,
            "one list has to mean every seal the reader holds, not the first one",
        )

    def test_the_list_stays_inside_the_readers_own_shop(self):
        """Merging two lists must not merge two shops."""
        mine = self._evaluation(self.survey, self.holder_company)
        theirs = self._evaluation(self.survey, self.other_company)

        listed = self._listed_by_holder()

        self.assertIn(mine, listed)
        self.assertNotIn(
            theirs,
            listed,
            "another shop's evaluation is not mine to read, one list or two",
        )

    def test_a_seal_not_held_is_not_listed(self):
        """Holding one seal does not open the other."""
        one_seal_only = self.env["res.users"].create(
            {
                "name": "One Seal Only",
                "login": "cert_one_seal",
                "company_id": self.holder_company.id,
                "company_ids": [(6, 0, self.holder_company.ids)],
                "group_ids": [
                    (6, 0, [self.env.ref("base.group_user").id, self.group_user.id])
                ],
            }
        )
        held = self._evaluation(self.survey, self.holder_company)
        not_held = self._evaluation(self.other_survey, self.holder_company)

        listed = (
            self.env["survey.user_input"].with_user(one_seal_only).search(LIST_DOMAIN)
        )

        self.assertIn(held, listed)
        self.assertNotIn(not_held, listed)

    def test_the_seal_is_groupable_from_the_list(self):
        """The grouping the single list defaults to has to exist as a field.

        `search_default_group_by_certification_type` is silently ignored when
        the filter behind it is missing, and the list would quietly come back
        flat with both seals mixed together — which is the shape this change
        set out to avoid.
        """
        self._evaluation(self.survey, self.holder_company)
        self._evaluation(self.other_survey, self.holder_company)

        grouped = (
            self.env["survey.user_input"]
            .with_user(self.holder)
            ._read_group(LIST_DOMAIN, groupby=["certification_type_id"])
        )

        self.assertEqual(
            len(grouped), 2, "the reader's two seals must come back as two groups"
        )
