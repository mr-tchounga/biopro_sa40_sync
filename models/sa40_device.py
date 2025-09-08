# models/sa40_device.py
from odoo import models, fields, api
from odoo import fields as ofields
from odoo.exceptions import UserError
import logging
from datetime import datetime
import time

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
        # notify
        # build message
        msg = f"Fetched {overall_fetched} users: created {overall_created}, updated {overall_updated}."
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Fetch Users Complete', 'message': msg, 'type': 'success'}
        }
            

    ####################################################################
    # Fetch attendances (no persistence)
    ####################################################################
    def fetch_attendances_from_device(self):
        results = []
        for device in self:
            zk = conn = None
            try:
                zk, conn = self._connect_to_device(device)
                conn.disable_device()
                attendances = conn.get_attendance() or []
                for a in attendances:
                    ts = getattr(a, 'timestamp', None)
                    # Keep timestamp as a python datetime object when possible
                    rec = {
                        'user_id': getattr(a, 'user_id', None),
                        'timestamp': ts,   # keep datetime, don't isoformat()
                        'status': getattr(a, 'status', None) if hasattr(a, 'status') else None,
                        'raw': str(a),
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
        LogModel = self.env['sa40.attendance.log']
        created = skipped = invalid = 0
        fetched = len(records or [])

        # Ensure the cursor is not in an aborted state from previous errors.
        # If there's nothing to rollback this is a no-op.
        try:
            self.env.cr.rollback()
        except Exception:
            # if rollback itself fails for some reason, just continue -
            # we'll still use savepoints below to isolate errors.
            pass

        for rec in records or []:
            # Local try only for non-DB issues (parsing etc.)
            try:
                device_user_id = rec.get('user_id')
                ts = rec.get('timestamp')
                status = rec.get('status')
                raw = rec.get('raw')

                _logger.debug("Persisting attendance rec: device=%s user=%s ts=%s raw=%s", device.id, device_user_id, ts, raw)

                # Validate timestamp: must exist and be parseable
                if not ts:
                    _logger.warning("Skipping attendance with missing timestamp: %s", rec)
                    invalid += 1
                    continue

                # Try parsing timestamp robustly (same logic as before)
                parsed_ts = None
                if isinstance(ts, datetime):
                    parsed_ts = ts
                elif isinstance(ts, str):
                    try:
                        parsed_ts = ofields.Datetime.to_datetime(ts)
                    except Exception:
                        try:
                            parsed_ts = datetime.fromisoformat(ts)
                        except Exception:
                            try:
                                parsed_ts = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                            except Exception:
                                _logger.warning("Skipping attendance with invalid timestamp format: %s", ts)
                                invalid += 1
                                continue
                else:
                    _logger.warning("Skipping attendance with unsupported timestamp type: %r", type(ts))
                    invalid += 1
                    continue

                # Isolate DB ops per-record in a savepoint so one bad record does not abort everything
                try:
                    with self.env.cr.savepoint():
                        # find linked partner via sa40.user if any (use sudo for search to avoid access issues)
                        user = self.env['sa40.user'].sudo().search([
                            ('device_id', '=', device.id),
                            '|', ('device_user_id', '=', device_user_id), ('device_uid', '=', device_user_id)
                        ], limit=1)
                        partner_id = user.partner_id.id if user and user.partner_id else False

                        vals = {
                            'device_id': device.id,
                            'log_user_uid': device_user_id,
                            'timestamp': parsed_ts,
                            'status': status,
                            'raw': raw,
                            'partner_id': partner_id,
                        }

                        LogModel.sudo().create(vals)
                        created += 1

                except Exception as db_exc:
                    # Any DB error (unique constraint, integrity error, etc.) will be rolled back
                    # to the savepoint automatically. Here we log and count it as skipped.
                    _logger.exception("DB error while creating attendance log (rolled back to savepoint): %s | rec=%s", db_exc, rec)
                    skipped += 1

            except Exception:
                # Any other unanticipated exception (parsing, etc.) - mark invalid
                _logger.exception('Unhandled error processing attendance record %s', rec)
                invalid += 1

        return {'created': created, 'skipped_duplicates': skipped, 'invalid': invalid, 'fetched': fetched}


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



    ####################################################################
    # Push users to device  (create/update)
    ####################################################################
    def push_sa40_users_to_device(self, user_domain=None, only_with_partner=False, debug=False):
        """
        Push sa40.user to device and ensure local sa40.user.name matches partner.name (if any).
        Returns counters including:
          - pushed
          - created_remote
          - updated_remote
          - updated_local
          - skipped
        """
        self._ensure_pyzk()
        Sa40User = self.env['sa40.user'].sudo()

        counters = {
            'pushed': 0,
            'created_remote': 0,
            'updated_remote': 0,
            'updated_local': 0,
            'skipped': 0
        }
        base_domain = user_domain or []

        for device in self:
            zk = conn = None
            try:
                zk, conn = self._connect_to_device(device)
                conn.disable_device()

                # read device users once (map uid -> name)
                dev_users = conn.get_users() or []
                dev_users_by_uid = {}
                for u in dev_users:
                    try:
                        dev_users_by_uid[int(getattr(u, 'uid', 0))] = getattr(u, 'name', '') or ''
                    except Exception:
                        continue
                used_uids = set(dev_users_by_uid.keys())
                max_uid = 0 if not used_uids else max(used_uids)

                domain = [('device_id', '=', device.id)] + base_domain
                if only_with_partner:
                    domain += [('partner_id', '!=', False)]
                users = Sa40User.search(domain)

                for user in users:
                    # ensure we operate on a fresh sudo record when writing
                    urec = user.sudo()

                    uid = int(urec.device_uid) if urec.device_uid else 0
                    if not uid:
                        max_uid += 1
                        while max_uid in used_uids:
                            max_uid += 1
                        uid = max_uid

                    user_id_param = str(urec.device_user_id or urec.device_uid or (urec.partner_id.id if urec.partner_id else urec.id))
                    card_val = 0
                    try:
                        if urec.partner_id and urec.partner_id.biometric_id and str(urec.partner_id.biometric_id).isdigit():
                            card_val = int(urec.partner_id.biometric_id)
                    except Exception:
                        card_val = 0

                    # PREFER partner name if present — this fixes the "I edited partner name but device got old name" case
                    desired_name = ''
                    if urec.partner_id and urec.partner_id.name:
                        desired_name = urec.partner_id.name
                    elif urec.name:
                        desired_name = urec.name
                    else:
                        desired_name = 'Unknown'
                    device_name = (desired_name)[:31]

                    # If partner name differs from sa40.user.name, update sa40.user BEFORE pushing so the push uses the new name
                    try:
                        if (urec.name or '') != desired_name:
                            try:
                                urec.write({'name': desired_name})
                                counters['updated_local'] += 1
                                if debug:
                                    _logger.info("LOCAL WRITE: updated sa40.user %s name -> %s", urec.id, desired_name)
                            except Exception:
                                _logger.exception("Failed to update local sa40.user.name for id %s", urec.id)
                    except Exception:
                        # just continue pushing even if local write fails
                        _logger.exception("Error while comparing/writing sa40.user name for id %s", urec.id)

                    prev_name = dev_users_by_uid.get(int(uid)) if uid in dev_users_by_uid else None

                    if debug:
                        _logger.info("PUSH DEBUG: device=%s sa40.user=%s uid=%s user_id=%s name=%s prev_name=%s card=%s",
                                     device.name, urec.id, uid, user_id_param, device_name, prev_name, card_val)

                    try:
                        success = conn.set_user(uid=int(uid),
                                                name=device_name,
                                                privilege=0,
                                                password='',
                                                group_id='',
                                                user_id=user_id_param,
                                                card=card_val)
                        _logger.info("PUSH RESULT: sa40.user=%s set_user returned %s (device=%s uid=%s)",
                                     urec.id, success, device.name, uid)

                        if success:
                            counters['pushed'] += 1

                            if prev_name is None or prev_name == '':
                                counters['created_remote'] += 1
                            elif str(prev_name).strip() != device_name:
                                counters['updated_remote'] += 1

                            # refresh our local cache for the run
                            dev_users_by_uid[int(uid)] = device_name
                        else:
                            counters['skipped'] += 1
                            _logger.warning("set_user returned False for sa40.user %s -> uid %s on device %s",
                                            urec.id, uid, device.name)
                            continue

                        used_uids.add(int(uid))

                    except Exception as exc:
                        _logger.exception("Failed to push sa40.user %s to device %s: %s", urec.id, device.name, exc)
                        counters['skipped'] += 1

            except Exception as exc:
                _logger.exception("Failed connecting/pushing to device %s", device.name)
                raise UserError(f"Failed to push users to device {device.name}: {exc}")
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

        return counters


    # wrapper callable from button
    def action_push_users(self):
        counters_total = {
            'pushed': 0,
            'created_remote': 0,
            'updated_remote': 0,
            'updated_local': 0,
            'skipped': 0
        }
        for device in self:
            try:
                res = device.push_sa40_users_to_device(user_domain=None, only_with_partner=False)
                for k in counters_total:
                    counters_total[k] += int(res.get(k, 0))
            except Exception as exc:
                _logger.exception("Error pushing sa40.users to device %s", device.name)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {'title': 'Push Failed', 'message': str(exc), 'sticky': False, 'type': 'warning'}
                }

        # msg = (f"Pushed {counters_total['pushed']} users — "
        #        f"created on device {counters_total['created_remote']}, "
        #        f"updated on device {counters_total['updated_remote']}, "
        #        f"local writes {counters_total['updated_local']}, "
        #        f"skipped {counters_total['skipped']}.")
        msg = 'Successfully pushed users to device(s).'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Push Complete', 'message': msg, 'type': 'success'}
        }

