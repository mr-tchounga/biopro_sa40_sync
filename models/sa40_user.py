
from odoo import models, fields, api

class Sa40User(models.Model):
    _name = 'sa40.user'
    _description = 'User from SA40 (device user)'

    name = fields.Char(required=True)
    device_id = fields.Many2one('sa40.device', required=True, ondelete='cascade')
    device_uid = fields.Integer(string='Device UID', help='Internal UID from device')
    device_user_id = fields.Char(string='Device user_id')
    partner_id = fields.Many2one('res.partner', string='Related Partner', help='Link to a partner (student/teacher)')

    _sql_constraints = [
        ('uniq_device_uid_per_device', 'unique(device_id, device_uid)', 'Device UID must be unique per device'),
    ]