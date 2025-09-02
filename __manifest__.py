{
    "name": "SA40 Biopro Sync",
    "version": "1.0.0",
    "summary": "Sync ZKTeco SA40 attendance & users into Odoo",
    "description": "Fetch logs from an external SA40 sync server and map them to hr.employee and hr.attendance.",
    "category": "Human Resources",
    "author": "Shifter",
    "depends": ["base", 'mail', "hr"],
    "data": [
        "security/ir.model.access.csv",
        "views/sa40_device_views.xml",
        "views/sa40_user_views.xml",
        "views/sa40_attendance_views.xml",
        "data/cron_data.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
