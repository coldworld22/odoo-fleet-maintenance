from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    maintenance_plan_ids = fields.One2many("fleet.maintenance.plan", "vehicle_id")
    maintenance_due_count = fields.Integer(
        compute="_compute_maintenance_due_count", string="Maintenance Due"
    )

    def _compute_maintenance_due_count(self):
        for vehicle in self:
            vehicle.maintenance_due_count = len(
                vehicle.maintenance_plan_ids.filtered(
                    lambda p: p.due_state in ("due_soon", "overdue")
                )
            )

    def action_view_maintenance_plans(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "fleet_maintenance_plan.action_fleet_maintenance_plan"
        )
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {"default_vehicle_id": self.id}
        return action
