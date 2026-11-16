import json

from odoo.tests import HttpCase, new_test_user, tagged

from .common import MaintenanceCase


@tagged("post_install", "-at_install")
class TestOdometerApi(HttpCase, MaintenanceCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.api_user = new_test_user(
            cls.env, login="telematics", groups="base.group_user,fleet.fleet_group_user"
        )
        apikeys = cls.env["res.users.apikeys"].with_user(cls.api_user)
        cls.key = apikeys._generate("rpc", "telematics")

    def post(self, payload, key=None):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return self.url_open("/api/fleet/v1/odometer", data=json.dumps(payload), headers=headers)

    def test_records_a_reading_and_reports_maintenance_status(self):
        self.make_plan(interval_km=5000)

        response = self.post({"license_plate": "ABC 1234", "value": 5100}, key=self.key)

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["odometer"], 5100)
        self.assertEqual(body["maintenance"][0]["state"], "overdue")
        self.assertEqual(self.vehicle.odometer, 5100)

    def test_rejects_requests_without_a_valid_key(self):
        self.assertEqual(self.post({"license_plate": "ABC 1234", "value": 10}).status_code, 401)
        self.assertEqual(
            self.post({"license_plate": "ABC 1234", "value": 10}, key="wrong").status_code, 401)

    def test_rejects_a_reading_lower_than_the_current_odometer(self):
        self.set_odometer(20000)

        response = self.post({"license_plate": "ABC 1234", "value": 1500}, key=self.key)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "odometer_decreased")

    def test_unknown_plate_and_bad_body(self):
        self.assertEqual(
            self.post({"license_plate": "NOPE", "value": 1}, key=self.key).status_code, 404)
        self.assertEqual(self.post({"value": "abc"}, key=self.key).status_code, 400)

    def test_maintenance_status_endpoint(self):
        self.make_plan(interval_km=5000)

        response = self.url_open("/api/fleet/v1/vehicles/ABC 1234/maintenance",
                                 headers={"Authorization": f"Bearer {self.key}"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["maintenance"][0]["plan"], "Oil change")
