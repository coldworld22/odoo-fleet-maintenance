{
    "name": "Fleet Maintenance Planning",
    "summary": "Preventive maintenance plans by mileage or date, with automatic service "
    "orders, purchase orders for parts, a QWeb service report and an odometer API",
    "version": "17.0.1.0.0",
    "category": "Human Resources/Fleet",
    "author": "Ayman Osman",
    "website": "https://github.com/coldworld22/odoo-fleet-maintenance",
    "license": "LGPL-3",
    "depends": ["fleet", "purchase"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/fleet_maintenance_plan_views.xml",
        "views/fleet_vehicle_views.xml",
        "views/fleet_vehicle_log_services_views.xml",
        "views/menus.xml",
        "report/service_order_report.xml",
    ],
    "installable": True,
    "application": False,
}
