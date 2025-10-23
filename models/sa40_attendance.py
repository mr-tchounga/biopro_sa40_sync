
from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class Sa40AttendanceLog(models.Model):
    _name = 'sa40.attendance.log'
    _description = 'SA40 attendance logs'

    device_id = fields.Many2one('sa40.device', required=True, ondelete='cascade')
    log_user_uid = fields.Char(string='Device User ID')
    timestamp = fields.Datetime(required=True)
    status = fields.Char()
    raw = fields.Text()

    user_id = fields.Many2one('res.users', string='Linked User', compute='_compute_user_id', store=True)
    def _compute_user_id(self):
        for record in self:
            # defensive: if no device or uid, clear user
            if not record.device_id or not record.log_user_uid:
                _logger.debug("No device_id or log_user_uid for log %s -> clearing user", record.id)
                record.user_id = False
                continue

            # do search as sudo to avoid permission issues in cron/imports
            user = self.env['sa40.user'].sudo().search(
                [('device_id', '=', record.device_id.id),
                 ('device_user_id', '=', record.log_user_uid)],
                limit=1
            )
            record.user_id = user.user_id.id if user and user.user_id else False

    _sql_constraints = [
        ('uniq_log_by_device_user_ts', 'unique(device_id, log_user_uid, timestamp)', 'Duplicate log for user and timestamp'),
    ]
    
    
    
    @api.model
    def create(self, vals):
        rec = super().create(vals)
        # fallback: ensure user set right away for new records (computes normally run,
        # but this guarantees it if something bypassed compute)
        if not rec.user_id and rec.device_id and rec.log_user_uid:
            try:
                rec._compute_user_id()
            except Exception as e:
                _logger.error("Error computing user for created log %s: %s", rec.id, e)
        return rec

    def write(self, vals):
        res = super().write(vals)
        # if device_id or log_user_uid changed, recompute user for these records
        if set(vals.keys()) & {'device_id', 'log_user_uid'}:
            try:
                # self is the recordset after write
                self._compute_user_id()
            except Exception as e:
                _logger.error("Error recomputing user on write for logs %s: %s", self.ids, e)
        return res
    
    
    
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
