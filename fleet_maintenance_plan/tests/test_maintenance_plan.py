from datetime import date

from freezegun import freeze_time

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import MaintenanceCase


@tagged("post_install", "-at_install")
class TestMaintenancePlan(MaintenanceCase):

    def test_next_due_is_counted_from_the_last_service(self):
        plan = self.make_plan(interval_km=10000, interval_months=6, start_date=date(2026, 1, 10))
        self.assertEqual(plan.next_due_date, date(2026, 7, 10))
        self.assertEqual(plan.next_due_odometer, 10000)

        plan.write({"last_service_date": date(2026, 5, 1), "last_service_odometer": 8200})

        self.assertEqual(plan.next_due_date, date(2026, 11, 1))
        self.assertEqual(plan.next_due_odometer, 18200)

    def test_a_plan_needs_at_least_one_interval(self):
        with self.assertRaises(ValidationError):
            self.make_plan(interval_km=0, interval_months=0)

    @freeze_time("2026-11-16")
    def test_due_state_by_mileage(self):
        plan = self.make_plan(interval_km=10000)
        self.set_odometer(9000)
        self.assertEqual(plan.due_state, "ok")

        self.set_odometer(9600)
        self.assertEqual(plan.due_state, "due_soon")

        self.set_odometer(10100)
        self.assertEqual(plan.due_state, "overdue")

    @freeze_time("2026-11-16")
    def test_due_state_by_date_whichever_comes_first(self):
        plan = self.make_plan(interval_km=10000, interval_months=6, start_date=date(2026, 5, 1))
        self.set_odometer(100)

        self.assertEqual(plan.next_due_date, date(2026, 11, 1))
        self.assertEqual(plan.due_state, "overdue", "date passed even though mileage is low")

    @freeze_time("2026-11-16")
    def test_due_state_is_searchable(self):
        overdue = self.make_plan(interval_months=6, start_date=date(2026, 1, 1))
        on_track = self.make_plan(name="Tyres", interval_months=12, start_date=date(2026, 10, 1))

        found = self.env["fleet.maintenance.plan"].search([("due_state", "=", "overdue")])

        self.assertIn(overdue, found)
        self.assertNotIn(on_track, found)

    def test_service_opens_a_purchase_order_for_parts(self):
        plan = self.make_plan(interval_km=10000, part_line_ids=[
            (0, 0, {"product_id": self.oil_filter.id, "quantity": 2}),
        ])

        service = plan.action_create_service()

        self.assertEqual(service.vehicle_id, self.vehicle)
        self.assertEqual(service.maintenance_plan_id, plan)
        order = service.purchase_order_id
        self.assertEqual(order.partner_id, self.workshop)
        self.assertEqual(order.order_line.product_id, self.oil_filter)
        self.assertEqual(order.order_line.product_qty, 2)
        self.assertIn("ABC 1234", order.origin)

    def test_parts_need_a_vendor(self):
        plan = self.make_plan(interval_km=10000, vendor_id=False, part_line_ids=[
            (0, 0, {"product_id": self.oil_filter.id, "quantity": 1}),
        ])
        with self.assertRaises(UserError):
            plan.action_create_service()

    @freeze_time("2026-11-16")
    def test_cron_opens_one_service_per_due_plan_and_is_idempotent(self):
        due = self.make_plan(interval_km=5000)
        not_due = self.make_plan(name="Tyres", interval_km=40000)
        self.set_odometer(5200)

        self.env["fleet.maintenance.plan"]._cron_generate_due_services()
        self.env["fleet.maintenance.plan"]._cron_generate_due_services()

        self.assertEqual(due.service_count, 1, "second run must not duplicate the open service")
        self.assertEqual(not_due.service_count, 0)

    @freeze_time("2026-11-16")
    def test_finishing_a_service_restarts_the_plan(self):
        plan = self.make_plan(interval_km=5000)
        self.set_odometer(5300)
        service = plan.action_create_service()

        service.write({"state": "done"})

        self.assertEqual(plan.last_service_date, date(2026, 11, 16))
        self.assertEqual(plan.last_service_odometer, 5300)
        self.assertEqual(plan.next_due_odometer, 10300)
        self.assertEqual(plan.due_state, "ok")

    def test_vehicle_shows_how_many_plans_are_due(self):
        self.make_plan(interval_km=5000)
        self.make_plan(name="Tyres", interval_km=40000)
        self.set_odometer(6000)

        self.assertEqual(self.vehicle.maintenance_due_count, 1)

    def test_service_order_report_renders(self):
        plan = self.make_plan(interval_km=5000, part_line_ids=[
            (0, 0, {"product_id": self.oil_filter.id, "quantity": 1}),
        ])
        service = plan.action_create_service()

        html, _format = self.env["ir.actions.report"]._render_qweb_html(
            "fleet_maintenance_plan.report_service_order", service.ids
        )

        html = html.decode()
        self.assertIn("ABC 1234", html)
        self.assertIn("Oil filter", html)
        self.assertIn(service.purchase_order_id.name, html)
