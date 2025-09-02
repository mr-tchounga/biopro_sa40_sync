# sa40_biopro_sync/models/sa40_attendance.py
from odoo import models, fields, api
from datetime import datetime
import dateutil.parser
from odoo import fields as odoofields

class SA40AttendanceRaw(models.Model):
    _name = "sa40.attendance.raw"
    _description = "Raw SA40 Attendance Record"

    device_id = fields.Many2one("sa40.device", required=True)
    user_id = fields.Many2one("sa40.user", string="Device User", required=True, ondelete='cascade')
    device_user_id = fields.Char(string="Device User ID", readonly=True)
    timestamp = fields.Datetime(string="Timestamp")
    status = fields.Char()
    raw = fields.Text()
    created_on = fields.Datetime(default=odoofields.Datetime.now, readonly=True)

    @api.model
    def ingest_records(self, device, records):
        """
        records: list of dicts with keys: user_id, timestamp, status, raw, etc.
        device: sa40.device record
        """
        Sa40User = self.env['sa40.user']
        Partner = self.env['res.partner']
        created = 0
        for r in records:
            # parse timestamp
            ts = r.get('timestamp')
            if ts:
                try:
                    dt = dateutil.parser.isoparse(ts)
                except Exception:
                    try:
                        dt = datetime.fromisoformat(ts)
                    except Exception:
                        dt = None
            else:
                dt = None

            # device's user identifier (badge/string)
            device_user_id = r.get('user_id') or r.get('uid') or r.get('user')

            # Try convert uid numeric if available
            uid_int = None
            try:
                uid_int = int(r.get('uid')) if r.get('uid') is not None else None
            except Exception:
                uid_int = None

            # Ensure we create or update the sa40.user record (device-specific)
            user_vals = {
                'name': str(device_user_id)[:60] or "user-%s" % (uid_int or "x"),
                'uid': uid_int or 0,
                'device_user_id': str(device_user_id) if device_user_id is not None else None,
                'privilege': r.get('privilege', None),
                'password': r.get('password', None),
                'group_id': r.get('group_id', None),
                'device_id': device.id,
                'note': r.get('raw') and str(r.get('raw')) or None,
            }
            user = Sa40User.create_or_update_from_device(user_vals)

            # check duplication: same device + device_user_id + timestamp
            domain = [
                ('device_id', '=', device.id),
                ('device_user_id', '=', str(device_user_id)),
            ]
            if dt:
                domain.append(('timestamp', '=', odoofields.Datetime.to_string(dt)))
            exists = self.search(domain, limit=1)
            if exists:
                continue

            record_vals = {
                'device_id': device.id,
                'user_id': user.id,
                'device_user_id': user.device_user_id,
                'timestamp': odoofields.Datetime.to_string(dt) if dt else odoofields.Datetime.now(),
                'status': r.get('status'),
                'raw': r.get('raw') or str(r),
            }
            self.create(record_vals)
            created += 1

            # attempt linking to partner if not linked yet
            if not user.partner_id and user.device_user_id:
                partner = Partner.search([('biometric_id', '=', user.device_user_id)], limit=1)
                if partner:
                    user.partner_id = partner.id

        return created
