"""Include installer tests in the same full unittest gate as the Study prototype."""
from pathlib import Path
import sys
import unittest


def load_tests(loader, standard_tests, pattern):
    directory = Path(__file__).resolve().parents[1] / 'deploy/ls5'
    sys.path.insert(0, str(directory))
    # A separate loader keeps nested discovery from changing prototype's import root.
    installer = unittest.TestLoader().discover(str(directory), pattern='test_*.py', top_level_dir=str(directory))
    return unittest.TestSuite([standard_tests, installer])
