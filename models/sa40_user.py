# sa40_biopro_sync/models/sa40_user.py
from odoo import models, fields, api

class SA40User(models.Model):
    _name = "sa40.user"
    _description = "SA40 Device User (biometric)"

    name = fields.Char(required=True)
    uid = fields.Integer(index=True, required=True)   # device UID (numeric)
    device_user_id = fields.Char(string="Device User ID", help="Badge / id shown on device")
    privilege = fields.Integer()
    password = fields.Char()
    group_id = fields.Char()
    device_id = fields.Many2one("sa40.device", ondelete="cascade", required=True)
    # Link to the school's person record (students/teachers/staff)
    partner_id = fields.Many2one("res.partner", string="Person / Partner",
                                 help="Linked person (student/teacher/staff). Use partner to represent persons in the school.")
    note = fields.Text(string="Raw device info")

    _sql_constraints = [
        ('uid_device_unique', 'unique(uid, device_id)', 'User UID must be unique per device')
    ]

    @api.model
    def create_or_update_from_device(self, vals):
        # Try to find existing by uid+device
        existing = self.search([('uid', '=', vals.get('uid')), ('device_id', '=', vals.get('device_id'))], limit=1)
        if existing:
            existing.sudo().write(vals)
            return existing
        return self.create(vals)

    @api.model
    def link_partners_by_device_id(self):
        """
        Attempt to link sa40.user to res.partner by comparing partner.biometric_id to this device_user_id.
        Adds field biometric_id to res.partner (see extension).
        """
        Partner = self.env['res.partner']
        for u in self.search([('partner_id', '=', False)]):
            if u.device_user_id:
                partner = Partner.search([('biometric_id', '=', u.device_user_id)], limit=1)
                if partner:
                    u.partner_id = partner.id
