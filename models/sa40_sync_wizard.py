from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class Sa40SyncLine(models.TransientModel):
    _name = 'sa40.sync.line'
    _description = 'Incoming SA40 log (transient)'

    wizard_id = fields.Many2one('sa40.sync.wizard', ondelete='cascade')
    log_user_uid = fields.Char(string='Device User ID')
    timestamp = fields.Datetime()
    status = fields.Char()
    raw = fields.Text()
    user_name = fields.Char(string='Linked User')  # was partner_name → renamed for consistency


class Sa40SyncWizard(models.TransientModel):
    _name = 'sa40.sync.wizard'
    _description = 'SA40 sync preview wizard'

    device_id = fields.Many2one('sa40.device', required=True)
    line_ids = fields.One2many('sa40.sync.line', 'wizard_id', string='Incoming logs')

    def persist_selected(self):
        """Persist the incoming transient lines into sa40.attendance.log."""
        count = 0
        for line in self.line_ids:
            # try to link to user if user_name exists
            user = False
            if line.user_name:
                user = self.env['res.users'].search([('name', '=', line.user_name)], limit=1)

            vals = {
                'device_id': self.device_id.id,
                'log_user_uid': line.log_user_uid,
                'timestamp': line.timestamp,
                'status': line.status,
                'raw': line.raw,
                'user_id': user.id if user else False,  # updated from partner_id → user_id
            }

            try:
                self.env['sa40.attendance.log'].create(vals)
                count += 1
            except Exception as e:
                _logger.warning("Skipping duplicate or invalid log (UID: %s): %s", line.log_user_uid, e)
                continue

        # Notify user on completion
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Import Complete',
                'message': f'Successfully imported {count} records.',
                'sticky': False,
                'type': 'success',
            }
        }
