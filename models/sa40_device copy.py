# models/sa40_device.py
from odoo import models, fields, api
from odoo import fields as ofields
from odoo.exceptions import UserError
import logging
from datetime import datetime, timezone
import re

# try import pyzk
try:
    from zk import ZK, const
except Exception:
    ZK = None
    const = None

_logger = logging.getLogger(__name__)


class Sa40Device(models.Model):
    _name = 'sa40.device'
    _description = 'SA40 Device record (Direct device integration)'

    name = fields.Char(required=True)
    device_ip = fields.Char(string='Device IP', required=True, default='192.168.1.201')
    device_port = fields.Integer(string='Device Port', required=True, default=4370)
    device_timeout = fields.Integer(string='Device timeout (s)', default=8)
    device_password = fields.Integer(string='Device password', default=0)
    active = fields.Boolean(default=True)
    note = fields.Char("Note")

    ####################################################################
    # Helpers
    ####################################################################
    def _ensure_pyzk(self):
        if ZK is None:
            raise UserError(
                "pyzk (ZK) library is not available in this Python environment. "
                "Install it or vendor it into the addon (see README)."
            )

    def _connect_to_device(self, device):
        """
        Connect to device and return (zk, conn).
        This method is robust to several pyzk constructor signatures.
        Caller MUST call conn.enable_device() and conn.disconnect() in finally.
        """
        self._ensure_pyzk()

        # attempt multiple ways to instantiate ZK (some forks use different signatures)
        zk = None
        last_exc = None
        try:
            # Common modern signature: positional ip, then named args
            zk = ZK(device.device_ip,
                    port=int(device.device_port),
                    timeout=int(device.device_timeout),
                    password=int(device.device_password),
                    force_udp=False)
        except TypeError as te:
            last_exc = te
            try:
                # Older signature: purely positional (ip, port, timeout, password, force_udp)
                zk = ZK(device.device_ip,
                        int(device.device_port),
                        int(device.device_timeout),
                        int(device.device_password),
                        False)
            except Exception as e2:
                last_exc = e2
                try:
                    # As a last attempt try keyword args but with ip= instead of host=
                    zk = ZK(ip=device.device_ip,
                            port=int(device.device_port),
                            timeout=int(device.device_timeout),
                            password=int(device.device_password),
                            force_udp=False)
                except Exception as e3:
                    last_exc = e3
                    # Give up and raise a helpful UserError
                    raise UserError(
                        "Failed to construct ZK object for pyzk. Tried multiple constructor signatures.\n"
                        f"Last error: {last_exc}\n"
                        "Check that pyzk is installed and compatible with this code."
                    )

        # connect
        conn = None
        try:
            conn = zk.connect()
            return zk, conn
        except Exception as exc:
            # cleanup on partial connect
            try:
                if conn:
                    conn.disconnect()
            except Exception:
                pass
            raise UserError(f"Failed to connect to device {device.device_ip}:{device.device_port} -> {exc}")

    ####################################################################
    # Test connectivity (UI button)
    ####################################################################
    def test_connectivity(self):
        self.ensure_one()
        if not self.id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Save first', 'message': 'Please save the device before testing.', 'sticky': False}
            }

        try:
            zk, conn = self._connect_to_device(self)
            try:
                conn.disable_device()
                msg = f"Connected to {self.name} ({self.device_ip})"
                _logger.info(msg)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {'title': 'Connection OK', 'message': msg, 'sticky': False, 'type': 'success'}
                }
            finally:
                try:
                    conn.enable_device()
                except Exception:
                    pass
                try:
                    conn.disconnect()
                except Exception:
                    pass
        except UserError as ue:
            _logger.exception('Connectivity test failed')
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Connection Failed', 'message': str(ue), 'sticky': False, 'type': 'warning'}
            }
        except Exception as exc:
            _logger.exception('Unexpected error during connectivity test')
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Connection Error', 'message': f'Unexpected error: {exc}', 'sticky': False, 'type': 'warning'}
            }


    ####################################################################
    # Fetch users (create/update)
    ####################################################################
    def fetch_users_from_device(self):
        """
        Fetch users directly from the biometric device and create/update sa40.user records.
        Returns a dict: {'fetched': n, 'created': x, 'updated': y, 'created_uids': [...]}
        """
        Sa40User = self.env['sa40.user']
        overall_fetched = overall_created = overall_updated = 0
        created_uids = []

        for device in self:
            zk = conn = None
            try:
                zk, conn = self._connect_to_device(device)
                conn.disable_device()
                uds = conn.get_users() or []
                fetched = len(uds)
                created = updated = 0

                for u in uds:
                    device_uid = getattr(u, 'uid', None)
                    device_user_id = getattr(u, 'user_id', None) or device_uid
                    name = getattr(u, 'name', None) or 'Unknown'

                    # find existing with sudo to avoid access rights issues
                    existing = Sa40User.sudo().search([
                        ('device_id', '=', device.id),
                        ('device_uid', '=', device_uid)
                    ], limit=1)

                    vals = {
                        'name': name,
                        'device_id': device.id,
                        'device_uid': device_uid,
                        'device_user_id': device_user_id,
                    }

                    if existing:
                        try:
                            existing.sudo().write(vals)
                            updated += 1
                        except Exception:
                            _logger.exception("Failed to update existing sa40.user %s for device %s", device_uid, device.name)
                    else:
                        try:
                            newrec = Sa40User.sudo().create(vals)
                            created += 1
                            created_uids.append(device_uid)
                        except Exception:
                            _logger.exception("Failed to create sa40.user %s for device %s", device_uid, device.name)

                overall_fetched += fetched
                overall_created += created
                overall_updated += updated

            except Exception as exc:
                _logger.exception('Failed to fetch users from device %s:%s', device.device_ip, device.device_port)
                # raise as UserError to show UI notification
                raise UserError(f"Failed to fetch users from device {device.name}: {exc}")
            finally:
                if conn:
                    try:
                        conn.enable_device()
                    except Exception:
                        pass
                    try:
                        conn.disconnect()
                    except Exception:
                        pass

        return {
            'fetched': overall_fetched,
            'created': overall_created,
            'updated': overall_updated,
            'created_uids': created_uids
        }

    
    # --- helper to parse timestamps robustly ---
    def _parse_timestamp(self, ts, raw=None):
        """
        Robust timestamp parser. Accepts:
        - datetime objects (returned as-is)
        - ISO-8601 strings
        - common formats like 'YYYY-MM-DD HH:MM:SS'
        - epoch seconds (int/str)
        - tries to extract date/time from `raw` string using regex
        Returns a Python datetime (timezone-unaware UTC) or None.
        """
        # 1) already a datetime
        if isinstance(ts, datetime):
            return ts

        # 2) numeric epoch (string or int)
        try:
            if ts is not None and (isinstance(ts, int) or (isinstance(ts, str) and ts.isdigit())):
                epoch = int(ts)
                # assume epoch seconds
                return datetime.fromtimestamp(epoch, tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            pass

        # 3) try Odoo's parser (handles many ISO forms)
        try:
            if isinstance(ts, str) and ts.strip():
                dt = ofields.Datetime.to_datetime(ts)
                if isinstance(dt, datetime):
                    return dt
        except Exception:
            pass

        # 4) try python's fromisoformat (strip trailing Z)
        try:
            if isinstance(ts, str) and ts.strip():
                s = ts.strip()
                if s.endswith('Z'):
                    s = s[:-1]
                # handle microseconds / timezone naive iso
                try:
                    return datetime.fromisoformat(s)
                except Exception:
                    # fallback below
                    pass
        except Exception:
            pass

        # 5) try common strptime formats
        common_formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S',
            '%d-%m-%Y %H:%M:%S',
            '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
        ]
        if isinstance(ts, str) and ts.strip():
            for fmt in common_formats:
                try:
                    return datetime.strptime(ts.strip(), fmt)
                except Exception:
                    continue

        # 6) try to extract a datetime-like substring from raw using regex
        if raw:
            # look for ISO-like groups: 2025-09-02 15:04:05 or 2025-09-02T15:04:05 or 02-09-2025 15:04:05
            patterns = [
                r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)',
                r'(\d{4}/\d{2}/\d{2}[ T]\d{2}:\d{2}:\d{2})',
                r'(\d{2}-\d{2}-\d{4}[ T]\d{2}:\d{2}:\d{2})',
                r'(\d{10,13})'  # epoch in seconds or ms
            ]
            for pat in patterns:
                m = re.search(pat, raw)
                if m:
                    candidate = m.group(1)
                    # if epoch-like numeric string
                    if candidate.isdigit():
                        try:
                            val = int(candidate)
                            # if it's millis (13 digits) convert to seconds
                            if len(candidate) >= 13:
                                val = val / 1000.0
                            return datetime.fromtimestamp(val, tz=timezone.utc).replace(tzinfo=None)
                        except Exception:
                            pass
                    # try iso/fromiso/strptime attempts on candidate
                    try:
                        dt = ofields.Datetime.to_datetime(candidate)
                        if isinstance(dt, datetime):
                            return dt
                    except Exception:
                        pass
                    for fmt in common_formats + ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%S%z']:
                        try:
                            # strip trailing Z before parsing if necessary
                            cs = candidate
                            if cs.endswith('Z'):
                                cs = cs[:-1]
                            return datetime.strptime(cs, fmt)
                        except Exception:
                            continue

        # nothing worked
        return None


    ####################################################################
    # Fetch attendances (no persistence)
    ####################################################################
    def fetch_attendances_from_device(self):
        """
        Fetch attendance records from device and return list of dicts:
        [{'user_id':..., 'timestamp': ISO-string or None, 'status':..., 'raw':...}, ...]
        """
        results = []
        for device in self:
            zk = conn = None
            try:
                zk, conn = self._connect_to_device(device)
                conn.disable_device()
                attendances = conn.get_attendance() or []
                for a in attendances:
                    ts = getattr(a, 'timestamp', None)
                    # keep raw string (repr) for debugging and timestamp fallback
                    raw = str(a)
                    rec = {
                        'user_id': getattr(a, 'user_id', None),
                        # keep original ts (may be None or datetime) — we'll parse later
                        'timestamp': ts.isoformat() if isinstance(ts, datetime) else (ts if ts is not None else None),
                        'status': getattr(a, 'status', None) if hasattr(a, 'status') else None,
                        'raw': raw,
                    }
                    results.append(rec)
            except Exception as exc:
                _logger.exception('Failed to fetch attendance from device %s:%s', device.device_ip, device.device_port)
                raise UserError(f"Failed to fetch attendance from {device.name}: {exc}")
            finally:
                if conn:
                    try:
                        conn.enable_device()
                    except Exception:
                        pass
                    try:
                        conn.disconnect()
                    except Exception:
                        pass
        return results

    ####################################################################
    # Persist attendances
    ####################################################################
    def persist_attendances(self, device, records):
        """
        Persist a list of attendance dicts into sa40.attendance.log for the given device (record).
        Returns {'created': x, 'skipped_duplicates': y, 'invalid': z, 'fetched': n, 'invalid_samples': [...]}
        """
        LogModel = self.env['sa40.attendance.log']
        created = skipped = invalid = 0
        fetched = len(records or [])
        invalid_samples = []

        for rec in records or []:
            try:
                device_user_id = rec.get('user_id')
                ts_raw = rec.get('timestamp')
                status = rec.get('status')
                raw = rec.get('raw')

                # parse timestamp robustly
                parsed_dt = self._parse_timestamp(ts_raw, raw)
                if parsed_dt is None:
                    invalid += 1
                    # collect sample (max 10) for debugging
                    if len(invalid_samples) < 10:
                        invalid_samples.append({'user_id': device_user_id, 'timestamp': ts_raw, 'raw': raw})
                    continue

                # convert parsed_dt to Odoo datetime string
                ts_string = ofields.Datetime.to_string(parsed_dt)

                # find linked partner via sa40.user (use sudo)
                user = self.env['sa40.user'].sudo().search([
                    ('device_id', '=', device.id),
                    '|', ('device_user_id', '=', device_user_id), ('device_uid', '=', device_user_id)
                ], limit=1)
                partner_id = user.partner_id.id if user and user.partner_id else False

                vals = {
                    'device_id': device.id,
                    'log_user_uid': device_user_id,
                    'timestamp': ts_string,
                    'status': status,
                    'raw': raw,
                    'partner_id': partner_id,
                }

                try:
                    LogModel.sudo().create(vals)
                    created += 1
                except Exception as e:
                    # likely duplicate by constraint; count as skipped
                    _logger.debug('Skipping attendance creation (likely duplicate) for %s: %s', vals, e)
                    skipped += 1

            except Exception:
                _logger.exception('Unhandled error processing attendance record %s', rec)
                invalid += 1

        # log a few invalid samples at WARN level for immediate debugging
        if invalid_samples:
            for s in invalid_samples:
                _logger.warning('SA40 invalid attendance sample: user=%s timestamp=%s raw=%s', s['user_id'], s['timestamp'], s['raw'])

        return {'created': created, 'skipped_duplicates': skipped, 'invalid': invalid, 'fetched': fetched, 'invalid_samples': invalid_samples}



    ####################################################################
    # High-level sync orchestration
    ####################################################################
    def sync_data(self, persist=True, preview=False):
        overall_users = {'fetched': 0, 'created': 0, 'updated': 0}
        overall_att = {'fetched': 0, 'created': 0, 'skipped_duplicates': 0, 'invalid': 0}

        for device in self:
            users_res = device.fetch_users_from_device()
            overall_users['fetched'] += users_res.get('fetched', 0)
            overall_users['created'] += users_res.get('created', 0)
            overall_users['updated'] += users_res.get('updated', 0)

            # fetch attendances for this device
            records = device.fetch_attendances_from_device()

            if preview:
                # build preview wizard like before
                wizard = self.env['sa40.sync.wizard'].create({'device_id': device.id})
                for rec in records:
                    device_user_id = rec.get('user_id')
                    ts = rec.get('timestamp')
                    status = rec.get('status')
                    raw = rec.get('raw')
                    partner_name = ''
                    user = self.env['sa40.user'].sudo().search([
                        ('device_id', '=', device.id),
                        '|', ('device_user_id', '=', device_user_id), ('device_uid', '=', device_user_id)
                    ], limit=1)
                    if user and user.partner_id:
                        partner_name = user.partner_id.name
                    self.env['sa40.sync.line'].create({
                        'wizard_id': wizard.id,
                        'log_user_uid': device_user_id,
                        'timestamp': ts,
                        'status': status,
                        'raw': raw,
                        'partner_name': partner_name,
                    })
                view = self.env.ref('your_module_name.view_sa40_sync_wizard_form', raise_if_not_found=False)
                return {
                    'name': 'Incoming SA40 Logs',
                    'type': 'ir.actions.act_window',
                    'res_model': 'sa40.sync.wizard',
                    'res_id': wizard.id,
                    'view_mode': 'form',
                    'views': [(view.id, 'form')] if view else False,
                    'view_id': view.id if view else False,
                    'target': 'new',
                }

            if persist:
                pers = device.persist_attendances(device, records)
                overall_att['fetched'] += pers.get('fetched', 0)
                overall_att['created'] += pers.get('created', 0)
                overall_att['skipped_duplicates'] += pers.get('skipped_duplicates', 0)
                overall_att['invalid'] += pers.get('invalid', 0)
            else:
                overall_att['fetched'] += len(records)

        # Build a verbose message
        msg = (
            f"Users: fetched {overall_users['fetched']}, created {overall_users['created']}, updated {overall_users['updated']}.\n"
            f"Attendance: fetched {overall_att['fetched']}, created {overall_att['created']}, "
            f"skipped (duplicates) {overall_att['skipped_duplicates']}, invalid {overall_att['invalid']}."
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'SA40 Sync Complete', 'message': msg, 'sticky': False, 'type': 'success'}
        }



    ####################################################################
    # Cron entrypoint for all devices
    ####################################################################
    @api.model
    def cron_sync_all_devices(self):
        devices = self.search([('active', '=', True)])
        for dev in devices:
            try:
                dev.sync_data(persist=True, preview=False)
            except Exception:
                _logger.exception('Error syncing device %s in cron', dev.name)
        return True
