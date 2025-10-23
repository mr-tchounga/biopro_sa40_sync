# 🔐 Odoo SA40 User Sync

This module integrates **Odoo** with **ZKTeco SA40 biometric devices**, allowing you to **push users** from Odoo to the device and keep them synchronized.

---

## 🚀 Features

- Push Odoo `sa40.user` records to SA40 devices.  
- Automatically create or update user info on devices:
  - ✅ Name (trimmed to 31 chars max)
  - ✅ User ID
  - ✅ UID (unique identifier on device)
  - ✅ Card number (from Partner Biometric ID if available)  
- Sync back `device_uid` and `device_user_id` into Odoo.  
- Handles multiple devices and avoids UID collisions.  
- Gracefully skips failed pushes and logs errors.  
- Manual **Push Users** button action per device.  

---

## ⚙️ How It Works

1. In Odoo, assign users to a device (`sa40.user` linked to `device_id`).  
2. Click **Push Users** on the device record.  
3. The system:
   - Connects to the device 🔌  
   - Disables it temporarily 📴  
   - Pushes or updates all assigned users 👥  
   - Re-enables the device ✅  

---

## 🛠️ Code Highlights

- **Main Push Logic** → `push_sa40_users_to_device()`  
- **UI Button** → `action_push_users()`  
- Uses `zk.set_user()` to write users on the device.  
- Updates Odoo records (`device_uid`, `device_user_id`) after a successful push.  

---

## 📊 Example Counters

When you push, you’ll get a nice summary:

```
Pushed 12 users — updated local 3, skipped 1.
```


| Counter        | Meaning                                      |
|----------------|----------------------------------------------|
| **pushed**     | Users successfully sent to the device        |
| **created_local** | Placeholder for local creation (future use) |
| **updated_local** | Users updated in Odoo after device push     |
| **skipped**    | Failed / skipped users                       |

---

## 🔧 Configuration

- Make sure your **ZKTeco SA40 device** is reachable (IP + port).  
- Ensure your Odoo `sa40.user` model contains:  
  - `name`  
  - `device_uid`  
  - `device_user_id`  
  - `user_id` (optional, used for card/biometric id)  
  - `device_id`  

---

## 📌 Notes

- Usernames are **truncated to 31 characters** (device limitation).  
- If no `device_uid` exists, the system auto-allocates one.  
- If the partner has a numeric `biometric_id`, it will be used as card number.  

---

## 🧑‍💻 Development

Clone and install in your Odoo `addons` directory:

```bash
git clone https://github.com/mr-tchounga/biopro_sa40_sync.git
