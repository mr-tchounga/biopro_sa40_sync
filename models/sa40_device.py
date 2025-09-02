# sa40_biopro_sync/models/sa40_device.py
from odoo import models, fields, api, _
import requests
from requests.exceptions import RequestException
from odoo.exceptions import UserError

class SA40Device(models.Model):
    _name = "sa40.device"
    _description = "SA40 Sync Device"

    name = fields.Char(required=True)
    protocol = fields.Selection([('http', 'http'), ('https', 'https')], default='http')
    device_ip = fields.Char(string="Device IP", required=True,
                            help="IP address of the SA40 device or of the sync server.")
    device_port = fields.Integer(string="Device Port", default=4370, required=True)
    # Optional path if your sync server uses a custom path or reverse-proxy:
    path = fields.Char(string="Path", help="Optional path (eg. /api/sa40). Leave empty for root", default="/")
    timeout = fields.Integer(string="Request timeout (sec)", default=15)
    active = fields.Boolean(default=True)
    create_external_attendance = fields.Boolean(
        string="Create external attendance records",
        default=False,
        help="If checked, attempt to create attendance records in linked system (custom logic)."
    )
    last_sync = fields.Datetime(readonly=True)

    def _base_url(self):
        """Build base URL from protocol, ip and port"""
        ip = (self.device_ip or "").strip()
        port = self.device_port or 0
        proto = self.protocol or "http"
        path = (self.path or "/").strip()
        # ensure path starts with /
        if not path.startswith("/"):
            path = "/" + path
        # remove trailing slash for concatenation convenience
        path = path.rstrip("/")
        return f"{proto}://{ip}:{port}{path}"

    def _get_sync_endpoint(self):
        """Return the full /sync endpoint URL for this device."""
        return self._base_url().rstrip("/") + "/sync"

    def action_sync_now(self):
        """Manual sync: call external /sync and ingest new records."""
        for device in self:
            url = device._get_sync_endpoint()
            try:
                resp = requests.post(url, timeout=device.timeout)
                resp.raise_for_status()
            except RequestException as e:
                raise UserError(_("Failed to contact %s: %s") % (url, e))
            try:
                data = resp.json()
            except Exception as e:
                raise UserError(_("Invalid JSON from %s: %s") % (url, e))

            if not data.get("ok"):
                raise UserError(_("Remote server error: %s") % (data,))
            new = data.get("new", [])
            # delegate ingestion to attendance model
            self.env['sa40.attendance.raw'].ingest_records(device, new)
            device.last_sync = fields.Datetime.now()
        return True
