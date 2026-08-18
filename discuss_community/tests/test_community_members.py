# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged

from .common import CommunityMixin


@tagged("post_install", "-at_install")
class TestCommunityShape(CommunityMixin, TransactionCase):
    """What a community member IS: groups, landing action, channel seats."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_fixtures()

    def test_member_holds_exactly_the_community_composition(self):
        """Internal + community marker + zone gate, and nothing portal.

        The composition is the contract every other feature reads: internal
        is what opens the Discuss backend, the marker is what strips the
        menus, and the zone gate is what lets the member READ the
        neighbourhood channels. ``share`` must be False -- it is the stored
        signal core uses for "portal-ish", and a community member being
        mistaken for portal would bounce them off ``/odoo``.
        """
        self.assertIn(self.internal_group, self.member.all_group_ids)
        self.assertIn(self.community_group, self.member.all_group_ids)
        self.assertIn(
            self.zone_gate_group,
            self.member.all_group_ids,
            "the zone-channel read gate must come along by implication",
        )
        self.assertFalse(self.member.share, "a community member is internal")
        self.assertTrue(self.member._is_internal())

    def test_employee_does_not_get_the_community_group(self):
        """The marker is standalone: being internal must not imply it.

        This is the group-design decision under test. If some future edit
        made ``group_community_member`` implied by ``base.group_user``, every
        merchant and staff account would wake up with a Discuss-only backend.
        """
        self.assertNotIn(self.community_group, self.employee.all_group_ids)

    def test_member_backend_is_discuss_and_only_discuss(self):
        """The visible menu set of a member is contained in the Discuss tree.

        Containment, not spot checks: asserting "Settings is hidden" would
        pass while any of the other two hundred roots leaked. The decoy root
        (visible to any internal user: no groups, a readable action) is the
        refutation half -- it proves the stripping is what hides it, not some
        accident of the decoy's own configuration.
        """
        Menu = self.env["ir.ui.menu"]
        decoy_action = self.env["ir.actions.act_window"].create(
            {
                "name": "DCM Decoy Partners",
                "res_model": "res.partner",
                "view_mode": "list,form",
            }
        )
        decoy_root = Menu.create({"name": "DCM Decoy Root"})
        Menu.create(
            {
                "name": "DCM Decoy Child",
                "parent_id": decoy_root.id,
                "action": "ir.actions.act_window,%d" % decoy_action.id,
            }
        )
        self.env.registry.clear_cache()

        member_visible = Menu.with_user(self.member)._visible_menu_ids()
        discuss_tree = set(
            Menu.sudo().search([("id", "child_of", self.discuss_root.id)]).ids
        )
        self.assertIn(self.discuss_root.id, member_visible, "Discuss itself is kept")
        self.assertLessEqual(
            set(member_visible),
            discuss_tree,
            "a community member must see nothing outside the Discuss tree",
        )
        self.assertNotIn(decoy_root.id, member_visible)

    def test_employee_menus_are_untouched(self):
        """A normal internal user keeps everything, decoy included.

        The stripping must be a property of the community GROUP, not a new
        platform-wide behaviour; this is the half that catches an override
        filtering the wrong population.
        """
        Menu = self.env["ir.ui.menu"]
        decoy_action = self.env["ir.actions.act_window"].create(
            {
                "name": "DCM Decoy Partners II",
                "res_model": "res.partner",
                "view_mode": "list,form",
            }
        )
        decoy_root = Menu.create({"name": "DCM Decoy Root II"})
        Menu.create(
            {
                "name": "DCM Decoy Child II",
                "parent_id": decoy_root.id,
                "action": "ir.actions.act_window,%d" % decoy_action.id,
            }
        )
        self.env.registry.clear_cache()

        employee_visible = Menu.with_user(self.employee)._visible_menu_ids()
        self.assertIn(self.discuss_root.id, employee_visible)
        self.assertIn(
            decoy_root.id,
            employee_visible,
            "an ordinary employee must keep seeing the rest of the backend",
        )

    def test_member_is_not_seated_in_the_employees_channel(self):
        """The staff's auto-subscribed 'general' channel excludes members.

        ``mail.channel_all_employees`` auto-seats every ``base.group_user``
        holder on user creation, and a community member IS one: without the
        carve-out in ``discuss_channel.py`` every walk-in guest would read
        the channel where staff talks to itself. The employee assertion is
        the control: the carve-out must remove exactly one population.
        """
        seats = (
            self.env["discuss.channel.member"]
            .sudo()
            .search(
                [
                    ("channel_id", "=", self.employees_channel.id),
                    (
                        "partner_id",
                        "in",
                        (self.member | self.employee).partner_id.ids,
                    ),
                ]
            )
        )
        self.assertEqual(
            seats.partner_id,
            self.employee.partner_id,
            "the employee is auto-seated, the community member is not",
        )


@tagged("post_install", "-at_install")
class TestCommunityLandingAndSignup(CommunityMixin, TransactionCase):
    """Where a member lands, and how signup decides who becomes one."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_fixtures()

    def _signup(self, login, **ctx):
        """Run the model half of an uninvited signup, with ``ctx`` as the
        request context the controller would have injected."""
        created = (
            self.env["res.users"]
            .sudo()
            .with_context(**ctx)
            ._signup_create_user(
                {
                    "login": login,
                    "email": login,
                    "name": "DCM %s" % login,
                    "password": "dcm_signup_pwd",
                }
            )
        )
        return created

    def test_member_home_action_is_discuss_and_is_valid(self):
        """``action_id`` points at the EXISTING Discuss client action.

        Half of this test is the orphan-action incident
        (``zca_platform/hooks.py``, step 8: a dangling ``action_id`` renders
        a blank backend): the action must not merely be set, it must exist,
        be the Discuss one, and be assignable without tripping core's
        ``_check_action_id`` constraint (which this write already proved by
        not raising).
        """
        promoted = self._signup(
            "dcm_action@example.com",
            community_signup=True,
            community_signup_zone="canarias",
        )
        # By id: `action_id`'s comodel is the base `ir.actions.actions`, the
        # ref is the concrete `ir.actions.client` -- same row, two models.
        self.assertEqual(promoted.action_id.id, self.discuss_action.id)
        self.assertTrue(
            self.env["ir.actions.actions"].sudo().browse(promoted.action_id.id).exists()
        )
        self.assertEqual(promoted.action_id.type, "ir.actions.client")
        # Internal + a valid Discuss home action: core's login redirect sends
        # internal users to /odoo and the web client opens the home action,
        # which is the whole landing story.
        self.assertTrue(promoted._is_internal())

    def test_website_signup_becomes_community_with_the_arrival_zone(self):
        """Signup on a neighbourhood site: internal + community + that zone.

        This is decision (4)+(5) end to end at the model layer: the context
        the controller injects is the input, the account shape and the
        channel seats are the observable output.
        """
        user = self._signup(
            "dcm_guanarteme@example.com",
            community_signup=True,
            community_signup_zone="guanarteme",
        )
        self.assertTrue(user._is_internal())
        self.assertIn(self.community_group, user.all_group_ids)
        self.assertEqual(user.chat_zone, "guanarteme")
        self.assertEqual(
            self._zone_channels_of(user),
            self.channel_general | self.channel_guanarteme,
        )
        # The arrival website's company must NOT land on the user: core's
        # `website` module writes the serving website's company into signup
        # values, and a resident owning a merchant's company is the exact
        # multi-company leak the platform already paid for once.
        self.assertEqual(user.company_id, self.main_company)
        self.assertEqual(user.company_ids, self.main_company)

    def test_general_site_signup_lands_in_the_general_channel_only(self):
        """Arrival through a `canarias` site means no neighbourhood.

        The platform's own sites carry the general zone; the member is a
        community member all the same, just seated nowhere in particular.
        """
        user = self._signup(
            "dcm_general@example.com",
            community_signup=True,
            community_signup_zone="canarias",
        )
        self.assertIn(self.community_group, user.all_group_ids)
        self.assertEqual(user.chat_zone, "canarias")
        self.assertEqual(self._zone_channels_of(user), self.channel_general)

    def test_signup_without_the_web_flag_stays_portal(self):
        """No flag, no promotion: core's portal default survives untouched.

        The flag only ever comes from the website signup controller, so this
        is the "backend-created users unaffected" guard: any other caller of
        ``signup()`` -- XML-RPC, a shell, another module -- keeps getting
        exactly what core gives.
        """
        user = self._signup("dcm_plain@example.com")
        self.assertTrue(user.share, "an unflagged signup must stay portal")
        self.assertNotIn(self.internal_group, user.all_group_ids)
        self.assertNotIn(self.community_group, user.all_group_ids)

    def test_invited_user_stays_portal_even_with_the_flag(self):
        """A token invitation wins over the website it is redeemed on.

        Core marks token signups by putting ``partner_id`` in the values;
        the promotion must refuse those even if the context flag is present,
        because the person who sent the invitation chose portal on purpose.
        """
        partner = self.env["res.partner"].create(
            {"name": "DCM Invited", "email": "dcm_invited@example.com"}
        )
        user = (
            self.env["res.users"]
            .sudo()
            .with_context(community_signup=True, community_signup_zone="guanarteme")
            ._signup_create_user(
                {
                    "login": "dcm_invited@example.com",
                    "partner_id": partner.id,
                    "password": "dcm_signup_pwd",
                }
            )
        )
        self.assertTrue(user.share, "an invited user must stay portal")
        self.assertNotIn(self.community_group, user.all_group_ids)
