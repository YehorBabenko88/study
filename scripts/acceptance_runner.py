"""Report actual PASS separately from discovered total and SKIP."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
mode = sys.argv[1]
if mode == "browser":
    suite = unittest.TestSuite()
    for file in sorted(Path.cwd().glob("test_*browser*.py")):
        suite.addTests(unittest.defaultTestLoader.discover(".", pattern=file.name))
else:
    suite = unittest.defaultTestLoader.discover(".", pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
failed = len(result.failures) + len(result.errors)
summary = {"kind": "real_browser" if mode == "browser" else "unit_and_static_contracts",
           "total": result.testsRun, "PASS": result.testsRun - failed - len(result.skipped),
           "SKIP": len(result.skipped), "FAIL_OR_ERROR": failed}
print(json.dumps(summary), flush=True)
# Browser setup skips cannot count as successful browser acceptance.
sys.exit(0 if result.wasSuccessful() and (mode != "browser" or not result.skipped) else 1)
