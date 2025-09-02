from . import models
import sys
import os

vendor_path = os.path.join(os.path.dirname(__file__), 'lib', 'pyzk')
if vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)
