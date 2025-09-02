
from odoo import models, fields

class Sa40SyncLine(models.TransientModel):
    _name = 'sa40.sync.line'
    _description = 'Incoming SA40 log (transient)'

    wizard_id = fields.Many2one('sa40.sync.wizard', ondelete='cascade')
    log_user_uid = fields.Char(string='Device User ID')
    timestamp = fields.Datetime()
    status = fields.Char()
    raw = fields.Text()
    partner_name = fields.Char(string='Linked Partner')


class Sa40SyncWizard(models.TransientModel):
    _name = 'sa40.sync.wizard'
    _description = 'SA40 sync preview wizard'

    device_id = fields.Many2one('sa40.device')
    line_ids = fields.One2many('sa40.sync.line', 'wizard_id', string='Incoming logs')

    def persist_selected(self):
        """Persist the incoming transient lines into sa40.attendance.log."""
        for line in self.line_ids:
            # try to link to partner if partner_name exists
            partner = False
            if line.partner_name:
                partner = self.env['res.partner'].search([('name', '=', line.partner_name)], limit=1)
            vals = {
                'device_id': self.device_id.id,
                'log_user_uid': line.log_user_uid,
                'timestamp': line.timestamp,
                'status': line.status,
                'raw': line.raw,
                'partner_id': partner.id if partner else False,
            }
            try:
                self.env['sa40.attendance.log'].create(vals)
            except Exception:
                # ignore duplicates or log errors
                pass
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Import Complete',
                'message': f'Imported {len(self.line_ids)} records.',
                'sticky': False,
            }
        }