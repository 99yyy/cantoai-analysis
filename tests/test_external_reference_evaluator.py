"""Include the standalone, synthetic-only evaluator tests in repository CI."""
from pathlib import Path
import subprocess
import sys
import unittest


class ExternalReferenceEvaluatorTests(unittest.TestCase):
    def run_suite(self, suite):
        package = Path(__file__).resolve().parents[1] / 'investigations' / 'external-reference-evaluator'
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(package / suite), '-v'],
                                capture_output=True, text=True, check=False, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_adapter_synthetic_suite(self):
        self.run_suite('tests')

    def test_engine_synthetic_suite(self):
        self.run_suite('vendor')


if __name__ == '__main__': unittest.main(verbosity=2)
