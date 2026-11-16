# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase, new_test_user

# Context that avoids sending welcome mails when creating test users.
NO_MAIL_CTX = {
    "no_reset_password": True,
    "tracking_disable": True,
    "mail_create_nosubscribe": True,
}


class CertificationCase(TransactionCase):
    """Shared fixtures: a small vertical with a 3-question scored survey.

    Each question is a simple choice worth 0 or 2 points (max 6). The
    thresholds are Bronze >= 2, Silver >= 4, Gold >= 6.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, **NO_MAIL_CTX))
        cls.group_user = cls.env["res.groups"].create(
            {
                "name": "Test Cert User",
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
        cls.group_manager = cls.env["res.groups"].create(
            {
                "name": "Test Cert Manager",
                "implied_ids": [
                    (4, cls.group_user.id),
                    (
                        4,
                        cls.env.ref(
                            "company_certification.group_certification_manager"
                        ).id,
                    ),
                ],
            }
        )
        cls.survey = cls.env["survey.survey"].create(
            {
                "title": "Test Certification Survey",
                "survey_type": "survey",
                "scoring_type": "scoring_without_answers",
                "access_mode": "public",
                "users_login_required": True,
            }
        )
        cls.questions = cls.env["survey.question"]
        for index in range(3):
            cls.questions += cls.env["survey.question"].create(
                {
                    "survey_id": cls.survey.id,
                    "title": "Question %s" % index,
                    "question_type": "simple_choice",
                    "sequence": index + 1,
                    "comments_message": "Advice %s" % index,
                    "suggested_answer_ids": [
                        (0, 0, {"value": "No", "answer_score": 0}),
                        (0, 0, {"value": "Yes", "answer_score": 2}),
                    ],
                }
            )
        cls.cert_type = cls.env["certification.type"].create(
            {
                "name": "Test Certification",
                "code": "testcert",
                "survey_id": cls.survey.id,
                "group_user_id": cls.group_user.id,
                "group_manager_id": cls.group_manager.id,
                "max_score": 6,
                "bronze_min": 2,
                "silver_min": 4,
                "gold_min": 6,
                "cooldown_months": 3,
                "validity_years": 1,
            }
        )
        cls.company = cls.env["res.company"].create({"name": "Certified Shop"})
        cls.user = new_test_user(
            cls.env,
            login="cert_user",
            groups="base.group_user",
            company_id=cls.company.id,
            company_ids=[(6, 0, cls.company.ids)],
            context=NO_MAIL_CTX,
        )
        cls.user.write({"group_ids": [(4, cls.group_user.id)]})
        cls.manager = new_test_user(
            cls.env,
            login="cert_manager",
            groups="base.group_user",
            company_id=cls.company.id,
            company_ids=[(6, 0, cls.company.ids)],
            context=NO_MAIL_CTX,
        )
        cls.manager.write({"group_ids": [(4, cls.group_manager.id)]})
        cls.plain_user = new_test_user(
            cls.env, login="cert_plain", groups="base.group_user", context=NO_MAIL_CTX
        )

    @classmethod
    def _run_evaluation(cls, yes_answers, company=None, user=None):
        """Complete an evaluation answering 'Yes' on ``yes_answers`` questions."""
        user = user or cls.user
        company = company or cls.company
        answer = cls.env["survey.user_input"].create(
            {
                "survey_id": cls.survey.id,
                "partner_id": user.partner_id.id,
                "company_id": company.id,
                "test_entry": False,
            }
        )
        for index, question in enumerate(cls.questions):
            suggested = question.suggested_answer_ids.sorted("answer_score")[
                -1 if index < yes_answers else 0
            ]
            cls.env["survey.user_input.line"].create(
                {
                    "user_input_id": answer.id,
                    "question_id": question.id,
                    "answer_type": "suggestion",
                    "suggested_answer_id": suggested.id,
                }
            )
        answer._mark_done()
        return answer
