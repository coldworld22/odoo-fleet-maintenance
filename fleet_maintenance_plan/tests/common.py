from odoo.tests.common import TransactionCase


class MaintenanceCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        brand = env["fleet.vehicle.model.brand"].create({"name": "Toyota"})
        model = env["fleet.vehicle.model"].create({"name": "Hilux", "brand_id": brand.id})
        cls.vehicle = env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "ABC 1234",
        })
        cls.oil_change = env["fleet.service.type"].create({
            "name": "Oil change", "category": "service",
        })
        cls.workshop = env["res.partner"].create({"name": "Dammam Auto Workshop"})
        cls.oil_filter = env["product.product"].create({
            "name": "Oil filter", "purchase_ok": True, "standard_price": 35.0,
        })

    def set_odometer(self, value, vehicle=None):
        self.env["fleet.vehicle.odometer"].create({
            "vehicle_id": (vehicle or self.vehicle).id, "value": value,
        })
        # fleet.vehicle.odometer is computed without dependencies, so drop cached values.
        self.env.invalidate_all()

    def make_plan(self, **values):
        return self.env["fleet.maintenance.plan"].create({
            "name": "Oil change",
            "vehicle_id": self.vehicle.id,
            "service_type_id": self.oil_change.id,
            "vendor_id": self.workshop.id,
            **values,
        })
