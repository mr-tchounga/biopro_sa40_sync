
# SA40 sync module for Odoo

Steps to install:
1. Put `sa40_sync` folder into your Odoo addons path.
2. On the Odoo server environment install `requests` (e.g. `pip install requests`).
3. Update the Apps list and install the module.
4. Create an SA40 Device record (Setup > SA40 > Devices). Set the IP and port of the Flask sync server (this is the machine running your provided `sa40_sync_server.py`).
5. Click "Test Connection" to verify connectivity.
6. Click "Fetch Users" to import device users into `sa40.user`.
7. Click "Sync (preview)" to fetch incoming logs and preview them in a popup before import.
8. Click "Import all" in the popup to persist the incoming logs into `sa40.attendance.log`.

Notes:
- The module expects the Flask server endpoints: `/users` and `/sync` as in your provided script.
- Map `sa40.user.partner_id` to your student/teacher `res.partner` records to link logs to people.
- If your school uses a different model for students (e.g., `school.student`), adapt relationships accordingly.