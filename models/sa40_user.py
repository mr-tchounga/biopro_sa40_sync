
from odoo import models, fields, api

class Sa40User(models.Model):
    _name = 'sa40.user'
    _description = 'User from SA40 (device user)'

    name = fields.Char(required=True)
    device_id = fields.Many2one('sa40.device', required=True, ondelete='cascade')
    device_uid = fields.Integer(string='Device UID', help='Internal UID from device')
    device_user_id = fields.Char(string='Device user_id')
    user_id = fields.Many2one('res.users', string='Related User', help='Link to a user (student/teacher)')

    _sql_constraints = [
        ('uniq_device_uid_per_device', 'unique(device_id, device_uid)', 'Device UID must be unique per device'),
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
