from odoo import fields, models


class FleetVehicleLogServices(models.Model):
    _inherit = "fleet.vehicle.log.services"

    maintenance_plan_id = fields.Many2one(
        "fleet.maintenance.plan", index=True, ondelete="set null"
    )
    purchase_order_id = fields.Many2one("purchase.order", string="Parts Order", copy=False)

    def write(self, vals):
        result = super().write(vals)
        if vals.get("state") == "done":
            self._restart_plans()
        return result

    def _restart_plans(self):
        """A finished service resets its plan's clock from that service's date and mileage."""
        today = fields.Date.context_today(self)
        for service in self.filtered("maintenance_plan_id"):
            service.maintenance_plan_id.write({
                "last_service_date": service.date or today,
                "last_service_odometer": service.odometer or service.vehicle_id.odometer,
            })
