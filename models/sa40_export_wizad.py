# models/sa40_export_wizard.py
import io
import csv
import base64
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError

# optional import for xlsx; handle gracefully
try:
    import openpyxl
    from openpyxl.workbook import Workbook
    OPENPYXL_AVAILABLE = True
except Exception:
    OPENPYXL_AVAILABLE = False


class Sa40ExportWizard(models.TransientModel):
    _name = 'sa40.export.wizard'
    _description = 'Export SA40 data (CSV / Excel)'

    model_choice = fields.Selection([
        ('attendance', 'Attendance logs'),
        ('users', 'Device users'),
    ], required=True, default='attendance')

    export_format = fields.Selection([
        ('csv', 'CSV'),
        ('xlsx', 'Excel (.xlsx)'),
    ], required=True, default='csv')

    export_selected = fields.Boolean(string='Export selected records (if any)', default=True,
                                     help='If true and active_ids are present they will be exported. Otherwise the domain filters apply.')
    device_id = fields.Many2one('sa40.device', string='Device (optional)',
                                help='Limit export to a specific device (applies to both models).')
    date_from = fields.Datetime(string='From (timestamp)', help='Only for Attendance logs: start timestamp (inclusive)')
    date_to = fields.Datetime(string='To (timestamp)', help='Only for Attendance logs: end timestamp (inclusive)')

    # internal: store active_ids passed via context
    active_ids = fields.Char(string='Active IDs (internal)', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # carry over active_ids from context into the wizard so we can export selected
        active_ids = self._context.get('active_ids') or []
        if active_ids:
            res['active_ids'] = ','.join(map(str, active_ids))
        return res

    def _get_selected_ids_list(self):
        if not self.active_ids:
            return []
        try:
            return [int(x) for x in self.active_ids.split(',') if x.strip()]
        except Exception:
            return []

    def action_export(self):
        """Main entrypoint called by button: build bytes -> ir.attachment -> return act_url"""
        self.ensure_one()

        # build domain / recordset depending on model_choice
        if self.export_selected:
            selected_ids = self._get_selected_ids_list()
        else:
            selected_ids = []

        if self.model_choice == 'attendance':
            Model = self.env['sa40.attendance.log'].sudo()
            domain = []
            if self.device_id:
                domain += [('device_id', '=', self.device_id.id)]
            if self.date_from:
                domain += [('timestamp', '>=', self.date_from)]
            if self.date_to:
                domain += [('timestamp', '<=', self.date_to)]
            if selected_ids:
                records = Model.browse(selected_ids)
            else:
                records = Model.search(domain)
            filename_base = 'sa40_attendance_export'
            headers = [
                'id', 'device_id', 'device_name', 'device_ip', 'log_user_uid',
                'timestamp', 'status', 'partner_id', 'partner_name', 'raw'
            ]
            rows = []
            for r in records:
                device_name = r.device_id.name if r.device_id else ''
                device_ip = getattr(r.device_id, 'device_ip', '') if r.device_id else ''
                ts = ''
                try:
                    ts = fields.Datetime.to_string(r.timestamp) if r.timestamp else ''
                except Exception:
                    ts = str(r.timestamp) if r.timestamp else ''
                partner_id = r.partner_id.id if r.partner_id else ''
                partner_name = r.partner_id.name if r.partner_id else ''
                rows.append([
                    r.id,
                    r.device_id.id if r.device_id else '',
                    device_name,
                    device_ip,
                    r.log_user_uid or '',
                    ts,
                    r.status or '',
                    partner_id,
                    partner_name,
                    (r.raw or '').replace('\n', '\\n'),
                ])
        else:
            # users
            Model = self.env['sa40.user'].sudo()
            domain = []
            if self.device_id:
                domain += [('device_id', '=', self.device_id.id)]
            if selected_ids:
                records = Model.browse(selected_ids)
            else:
                records = Model.search(domain)
            filename_base = 'sa40_users_export'
            headers = ['id', 'name', 'device_id', 'device_name', 'device_uid', 'device_user_id', 'partner_id', 'partner_name']
            rows = []
            for u in records:
                device_name = u.device_id.name if u.device_id else ''
                partner_id = u.partner_id.id if u.partner_id else ''
                partner_name = u.partner_id.name if u.partner_id else ''
                rows.append([
                    u.id,
                    u.name or '',
                    u.device_id.id if u.device_id else '',
                    device_name,
                    u.device_uid or '',
                    u.device_user_id or '',
                    partner_id,
                    partner_name,
                ])

        # Dispatch to CSV or XLSX generator
        if self.export_format == 'csv':
            data_bytes = self._build_csv_bytes(headers, rows)
            fname = f"{filename_base}_{fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.now())).replace(' ', '_').replace(':','-')}.csv"
            mimetype = 'text/csv'
        else:
            # xlsx
            if not OPENPYXL_AVAILABLE:
                raise UserError(_("The Python library 'openpyxl' is required to export to XLSX. Install it on the server or switch to CSV."))
            data_bytes = self._build_xlsx_bytes(headers, rows)
            fname = f"{filename_base}_{fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.now())).replace(' ', '_').replace(':','-')}.xlsx"
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

        # create attachment
        attachment = self.env['ir.attachment'].create({
            'name': fname,
            'type': 'binary',
            'datas': base64.b64encode(data_bytes).decode('utf-8'),
            'datas_fname': fname,
            'mimetype': mimetype,
            # no res_model/res_id -> generic attachment
        })

        url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }

    def _build_csv_bytes(self, headers, rows):
        buff = io.StringIO()
        writer = csv.writer(buff)
        writer.writerow(headers)
        for row in rows:
            # ensure strings and avoid newlines in fields (escape)
            writer.writerow([str(c) if c is not None else '' for c in row])
        return buff.getvalue().encode('utf-8')

    def _build_xlsx_bytes(self, headers, rows):
        # create workbook, write header and rows
        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for row in rows:
            # convert datetimes or other objects to strings
            newrow = []
            for c in row:
                if isinstance(c, datetime):
                    newrow.append(c)
                else:
                    newrow.append(c)
            ws.append(newrow)
        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()
