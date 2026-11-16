"""REST endpoints for telematics devices and other systems.

Callers authenticate with a standard Odoo API key (Preferences → Account Security →
New API Key) sent as ``Authorization: Bearer <key>``. Requests then run as that key's
user, so normal access rights and record rules apply.
"""

import json
import logging

from odoo import fields, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


def _json(payload, status=200):
    return request.make_response(
        json.dumps(payload, default=str),
        headers=[("Content-Type", "application/json")],
        status=status,
    )


def _error(status, code, message):
    return _json({"error": {"code": code, "message": message}}, status=status)


class FleetMaintenanceApi(http.Controller):

    def _authenticate(self):
        header = request.httprequest.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        key = header[len("Bearer "):].strip()
        uid = request.env["res.users.apikeys"]._check_credentials(scope="rpc", key=key)
        if uid:
            request.update_env(user=uid)
        return uid

    def _vehicle_by_plate(self, plate):
        return request.env["fleet.vehicle"].search([("license_plate", "=", plate)], limit=1)

    @http.route("/api/fleet/v1/odometer", type="http", auth="none", methods=["POST"],
                csrf=False, save_session=False)
    def post_odometer(self):
        """Record a reading: {"license_plate": "ABC 1234", "value": 15230, "date": "2026-11-16"}.

        Readings lower than the vehicle's current odometer are rejected, because they
        almost always mean a typo or a swapped device, and they would push every
        mileage-based plan backwards.
        """
        if not self._authenticate():
            return _error(401, "unauthorized", "Missing or invalid API key.")
        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            plate = str(body["license_plate"]).strip()
            value = float(body["value"])
            date = fields.Date.to_date(body.get("date")) or fields.Date.context_today(
                request.env["fleet.vehicle"])
        except (KeyError, TypeError, ValueError):
            return _error(400, "invalid_request",
                          "Expected JSON with license_plate, value and an optional date.")

        try:
            vehicle = self._vehicle_by_plate(plate)
            if not vehicle:
                return _error(404, "vehicle_not_found", f"No vehicle with plate {plate}.")
            if value < vehicle.odometer:
                return _error(409, "odometer_decreased",
                              f"Reading {value} is below the current {vehicle.odometer}.")
            request.env["fleet.vehicle.odometer"].create({
                "vehicle_id": vehicle.id, "value": value, "date": date,
            })
        except (AccessError, ValidationError) as e:
            return _error(403, "forbidden", str(e))

        return _json({
            "vehicle_id": vehicle.id,
            "odometer": vehicle.odometer,
            "maintenance": self._plans_payload(vehicle),
        })

    @http.route("/api/fleet/v1/vehicles/<string:plate>/maintenance", type="http",
                auth="none", methods=["GET"], csrf=False, save_session=False)
    def get_maintenance(self, plate):
        """Maintenance status for one vehicle, e.g. for a driver app."""
        if not self._authenticate():
            return _error(401, "unauthorized", "Missing or invalid API key.")
        vehicle = self._vehicle_by_plate(plate)
        if not vehicle:
            return _error(404, "vehicle_not_found", f"No vehicle with plate {plate}.")
        return _json({"vehicle_id": vehicle.id, "odometer": vehicle.odometer,
                      "maintenance": self._plans_payload(vehicle)})

    @staticmethod
    def _plans_payload(vehicle):
        return [{
            "plan": plan.name,
            "state": plan.due_state,
            "next_due_date": plan.next_due_date,
            "next_due_odometer": plan.next_due_odometer or None,
        } for plan in vehicle.maintenance_plan_ids]
