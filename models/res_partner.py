# sa40_biopro_sync/models/res_partner_ext.py
from odoo import models, fields

class ResPartner(models.Model):
    _inherit = "res.partner"

    biometric_id = fields.Char(string="Biometric ID", help="ID used on biometric device (badge/user id)")
    role = fields.Selection([('student', 'Student'), ('teacher', 'Teacher'), ('staff', 'Staff'), ('other', 'Other')], default='student')
