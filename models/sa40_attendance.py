
from odoo import models, fields

class Sa40AttendanceLog(models.Model):
    _name = 'sa40.attendance.log'
    _description = 'SA40 attendance logs'

    device_id = fields.Many2one('sa40.device', required=True, ondelete='cascade')
    log_user_uid = fields.Char(string='Device User ID')
    timestamp = fields.Datetime(required=True)
    status = fields.Char()
    raw = fields.Text()
    partner_id = fields.Many2one('res.partner', string='Linked Partner')

    _sql_constraints = [
        ('uniq_log_by_device_user_ts', 'unique(device_id, log_user_uid, timestamp)', 'Duplicate log for user and timestamp'),
    ]