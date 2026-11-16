# Fleet Maintenance Planning for Odoo 17

[![CI](https://github.com/coldworld22/odoo-fleet-maintenance/actions/workflows/ci.yml/badge.svg)](https://github.com/coldworld22/odoo-fleet-maintenance/actions/workflows/ci.yml)

An Odoo 17 module for preventive maintenance in the standard **Fleet** app. You set a plan such as
"oil change every 10,000 km or 6 months, whichever comes first". When the plan falls due, the module
opens the service record, raises the **purchase order** for the parts, prints a service order for the
workshop and resets the plan once the job is done. Telematics devices can push odometer readings over
a REST API.

**Stack:** Python · Odoo ORM · Fleet + Purchase · XML views · QWeb report · HTTP controller · Odoo test
framework · GitHub Actions

## Features

| | |
|---|---|
| **Maintenance plans** | Per vehicle, by mileage, by months, or both (whichever comes first). The next due date and next due odometer are computed and stored. |
| **Due status** | *On Track*, *Due Soon* (within 14 days or 500 km) or *Overdue*. It is shown as list colours and a status bar, and you can filter on it. |
| **Daily scheduled action** | Opens a service record for every plan that is due. It is idempotent: a plan that already has an open service is skipped. |
| **Purchase integration** | Parts listed on the plan become a purchase order to the plan's vendor, linked to the service. |
| **Closing the loop** | Marking a service *Done* resets its plan from that service's date and mileage. |
| **QWeb report** | Printable *Service Order* listing the vehicle, plate, driver, odometer, work, parts, purchase order and signatures. |
| **Vehicle form** | Smart button with the number of plans due for that vehicle. |
| **REST API** | Telematics devices post odometer readings; driver apps read maintenance status. |
| **Security** | Uses the Fleet user and manager groups, and a multi-company record rule. API calls run as the API key's user, so normal access rights apply. |

## Data model

```
fleet.vehicle ─────────< fleet.maintenance.plan >───── fleet.service.type
                               │          │
                               │          └──< fleet.maintenance.plan.part >── product.product
                               │
                               └──< fleet.vehicle.log.services ──> purchase.order
                                       (+ maintenance_plan_id, purchase_order_id)
```

The module adds one model (plus its part lines) and extends three standard ones: `fleet.vehicle`,
`fleet.vehicle.log.services` and their views. It reuses Fleet's service records and Purchase's
orders instead of creating parallel ones, so the standard reports, approvals and accounting work as
they do without the module.

## REST API

Create an API key in Odoo (*Preferences → Account Security → New API Key*) for a user in the Fleet
group, then send it as a bearer token.

```bash
# Record an odometer reading
curl -X POST https://odoo.example.com/api/fleet/v1/odometer \
  -H "Authorization: Bearer $ODOO_API_KEY" -H "Content-Type: application/json" \
  -d '{"license_plate": "ABC 1234", "value": 15230, "date": "2026-11-16"}'
```

```json
{
  "vehicle_id": 7,
  "odometer": 15230.0,
  "maintenance": [
    {"plan": "Oil change", "state": "due_soon", "next_due_date": "2027-01-10", "next_due_odometer": 15500.0}
  ]
}
```

```bash
# Maintenance status for one vehicle
curl https://odoo.example.com/api/fleet/v1/vehicles/ABC%201234/maintenance \
  -H "Authorization: Bearer $ODOO_API_KEY"
```

| Status | When |
|---|---|
| `401` | Missing or invalid API key |
| `400` | Body isn't JSON with `license_plate` and `value` |
| `404` | No vehicle with that plate |
| `409` | Reading is lower than the current odometer. It would usually be a typo or a swapped device, and it would move every mileage-based plan backwards. |

## Design decisions

- **Reuse Fleet and Purchase records, don't duplicate them.** A due plan opens a normal
  `fleet.vehicle.log.services` record and a normal `purchase.order`. Fleet managers keep working in
  screens they already know, and costs flow into Purchase and Accounting as usual.
- **Stored next-due fields, computed due status.** The next due date and mileage only change when the
  plan or its last service changes, so they are stored and indexed. The *due status* also depends on
  today's date and the live odometer, so it is computed on read. It has a custom `search` method so
  list filters and the scheduled action can still use it.
- **Idempotent scheduled action.** The daily job skips plans that already have an open service. A
  re-run, or a manual run from the form, never creates duplicate work orders or purchase orders.
- **API keys, not passwords.** The API uses Odoo's built-in API keys. Each device can have its own key,
  and a key can be revoked without touching the user's password.

## Install

1. Copy `fleet_maintenance_plan/` into your addons path.
2. Update the app list and install **Fleet Maintenance Planning**. It depends on `fleet` and
   `purchase`.
3. Go to *Fleet → Fleet → Maintenance Plans*.

## Tests

CI installs the module into a fresh Odoo 17 database (official `odoo:17.0` image with PostgreSQL) and
runs its tests. To run them locally against your own Odoo:

```bash
odoo -d test_db -i fleet_maintenance_plan --test-enable \
     --test-tags /fleet_maintenance_plan --stop-after-init
```

The tests cover:

- the due-date and due-mileage calculations, including "whichever comes first"
- searching on due status
- the purchase order raised for parts, and the vendor check
- the scheduled action, including its idempotency
- resetting a plan when a service is done
- the QWeb report
- every REST API response: success, 401, 400, 404 and 409

## License

LGPL-3
