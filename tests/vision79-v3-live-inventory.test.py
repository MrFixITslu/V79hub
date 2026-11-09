"""Exercise the standalone inventory's synthetic safety cases."""
import importlib.util
from pathlib import Path
import sys
import unittest
path=Path(__file__).resolve().parents[1]/'scripts'/'vision79-v3-live-inventory.py'
spec=importlib.util.spec_from_file_location('v79_inventory',path)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
SafetyTests=module.SafetyTests
if __name__=='__main__':unittest.main()
