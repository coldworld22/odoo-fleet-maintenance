from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# How early a plan counts as "due soon".
DUE_SOON_DAYS = 14
DUE_SOON_KM = 500


class FleetMaintenancePlan(models.Model):
    """A recurring maintenance rule for one vehicle, e.g. "oil change every 10,000 km or
    6 months, whichever comes first". When it falls due, a service record is opened in
    the standard Fleet app and, if the plan lists parts, a purchase order is raised."""

    _name = "fleet.maintenance.plan"
    _description = "Fleet Maintenance Plan"
    _inherit = ["mail.thread"]
    _order = "next_due_date, id"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    vehicle_id = fields.Many2one(
        "fleet.vehicle", required=True, ondelete="cascade", index=True, tracking=True
    )
    service_type_id = fields.Many2one("fleet.service.type", required=True)
    vendor_id = fields.Many2one(
        "res.partner", string="Default Vendor", help="Workshop or supplier for parts."
    )

    interval_km = fields.Float(string="Every (km)", tracking=True)
    interval_months = fields.Integer(string="Every (months)", tracking=True)

    start_date = fields.Date(required=True, default=fields.Date.context_today)
    last_service_date = fields.Date(tracking=True)
    last_service_odometer = fields.Float(tracking=True)

    next_due_date = fields.Date(compute="_compute_next_due", store=True)
    next_due_odometer = fields.Float(compute="_compute_next_due", store=True)
    current_odometer = fields.Float(related="vehicle_id.odometer")
    due_state = fields.Selection(
        [("ok", "On Track"), ("due_soon", "Due Soon"), ("overdue", "Overdue")],
        compute="_compute_due_state",
        search="_search_due_state",
    )

    part_line_ids = fields.One2many("fleet.maintenance.plan.part", "plan_id", copy=True)
    service_ids = fields.One2many("fleet.vehicle.log.services", "maintenance_plan_id")
    service_count = fields.Integer(compute="_compute_service_count")

    _sql_constraints = [
        (
            "positive_intervals",
            "CHECK(interval_km >= 0 AND interval_months >= 0)",
            "Intervals can't be negative.",
        ),
    ]

    @api.constrains("interval_km", "interval_months")
    def _check_interval(self):
        for plan in self:
            if not plan.interval_km and not plan.interval_months:
                raise ValidationError(
                    _("Plan %s needs a mileage interval, a time interval, or both.", plan.name)
                )

    @api.depends("interval_km", "interval_months", "start_date", "last_service_date",
                 "last_service_odometer")
    def _compute_next_due(self):
        for plan in self:
            base_date = plan.last_service_date or plan.start_date
            plan.next_due_date = (
                base_date + relativedelta(months=plan.interval_months)
                if plan.interval_months and base_date
                else False
            )
            plan.next_due_odometer = (
                plan.last_service_odometer + plan.interval_km if plan.interval_km else 0.0
            )

    @api.depends("next_due_date", "next_due_odometer", "vehicle_id.odometer")
    def _compute_due_state(self):
        today = fields.Date.context_today(self)
        for plan in self:
            plan.due_state = plan._due_state_on(today)

    def _due_state_on(self, today):
        self.ensure_one()
        odometer = self.vehicle_id.odometer
        by_date = self.next_due_date
        by_km = self.next_due_odometer if self.interval_km else 0.0
        if (by_date and by_date <= today) or (by_km and odometer >= by_km):
            return "overdue"
        if (by_date and by_date <= today + relativedelta(days=DUE_SOON_DAYS)) or (
            by_km and odometer >= by_km - DUE_SOON_KM
        ):
            return "due_soon"
        return "ok"

    def _search_due_state(self, operator, value):
        # The state depends on today's date and the live odometer, so it can't be stored.
        # Fleets are hundreds of vehicles, not millions, so evaluating in Python is fine.
        if operator not in ("=", "!=", "in", "not in"):
            raise UserError(_("Unsupported search on due state."))
        values = [value] if isinstance(value, str) else list(value)
        matching = self.search([]).filtered(lambda p: p.due_state in values)
        positive = operator in ("=", "in")
        return [("id", "in" if positive else "not in", matching.ids)]

    def _compute_service_count(self):
        counts = {
            plan.id: count
            for plan, count in self.env["fleet.vehicle.log.services"]._read_group(
                [("maintenance_plan_id", "in", self.ids)],
                groupby=["maintenance_plan_id"],
                aggregates=["__count"],
            )
        }
        for plan in self:
            plan.service_count = counts.get(plan.id, 0)

    def _open_service(self):
        self.ensure_one()
        return self.service_ids.filtered(lambda s: s.state in ("new", "running"))[:1]

    def action_create_service(self):
        """Open a service record (and a purchase order for parts) unless one is already
        open for this plan, so running it twice never duplicates work."""
        services = self.env["fleet.vehicle.log.services"]
        for plan in self:
            if plan._open_service():
                continue
            purchase = plan._create_parts_purchase_order()
            services |= services.create({
                "vehicle_id": plan.vehicle_id.id,
                "service_type_id": plan.service_type_id.id,
                "vendor_id": plan.vendor_id.id,
                "description": plan.name,
                "maintenance_plan_id": plan.id,
                "purchase_order_id": purchase.id,
            })
            plan.message_post(body=_("Service order created: %s", plan.name))
        return services

    def _create_parts_purchase_order(self):
        self.ensure_one()
        if not self.part_line_ids:
            return self.env["purchase.order"]
        if not self.vendor_id:
            raise UserError(_("Set a default vendor on plan %s to order its parts.", self.name))
        return self.env["purchase.order"].create({
            "partner_id": self.vendor_id.id,
            "company_id": self.company_id.id,
            "origin": f"{self.vehicle_id.license_plate or self.vehicle_id.name} / {self.name}",
            "order_line": [
                fields.Command.create({
                    "product_id": line.product_id.id,
                    "product_qty": line.quantity,
                    "product_uom": line.product_id.uom_po_id.id,
                })
                for line in self.part_line_ids
            ],
        })

    @api.model
    def _cron_generate_due_services(self):
        """Daily job: open services for every plan that is overdue or due soon."""
        due = self.search([("due_state", "in", ["overdue", "due_soon"])])
        return due.action_create_service()

    def action_view_services(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Services"),
            "res_model": "fleet.vehicle.log.services",
            "view_mode": "tree,form",
            "domain": [("maintenance_plan_id", "=", self.id)],
            "context": {
                "default_maintenance_plan_id": self.id,
                "default_vehicle_id": self.vehicle_id.id,
                "default_service_type_id": self.service_type_id.id,
            },
        }


class FleetMaintenancePlanPart(models.Model):
    _name = "fleet.maintenance.plan.part"
    _description = "Part used by a maintenance plan"

    plan_id = fields.Many2one("fleet.maintenance.plan", required=True, ondelete="cascade")
    product_id = fields.Many2one(
        "product.product", required=True, domain=[("purchase_ok", "=", True)]
    )
    quantity = fields.Float(default=1.0, required=True)

    _sql_constraints = [
        ("positive_quantity", "CHECK(quantity > 0)", "Part quantity must be positive."),
    ]
