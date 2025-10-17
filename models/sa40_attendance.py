
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
    
    
    def action_open_export_wizard(self):
        """Open the export wizard with active_ids from selected records."""
        ctx = dict(self.env.context or {})
        if self._name in ('sa40.attendance.log', 'sa40.user'):
            ctx = dict(ctx, active_ids=','.join(map(str, self.ids)) if self.ids else ctx.get('active_ids', []))
        wiz = self.env['sa40.export.wizard'].create({'active_ids': ctx.get('active_ids') or ''})
        view = self.env.ref('your_module_name.view_sa40_export_wizard_form', raise_if_not_found=False)
        return {
            'name': 'Export SA40 Data',
            'type': 'ir.actions.act_window',
            'res_model': 'sa40.export.wizard',
            'res_id': wiz.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')] if view else False,
            'target': 'new',
            'context': ctx,
        }
