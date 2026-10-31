import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

from scripts.operations.objective2_readiness import inspect, check_aws
from scripts.security.check_tracked_files import findings


class ReadinessTests(unittest.TestCase):
    def test_empty_root_is_not_deployed(self):
        with tempfile.TemporaryDirectory() as temp:
            report = inspect(Path(temp))
            self.assertFalse(report["all_dataset_marts_published"])
            self.assertFalse(report["local_sources"]["global_ibtracs"]["available"])
            self.assertFalse(report["published_marts"]["ibtracs"]["published"])

    def test_local_sources_do_not_require_cloud_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "raw" / "cyclones" / "ibtracs" / "ibtracs.ALL.list.v04r01.csv"
            source.parent.mkdir(parents=True)
            source.write_text("test")
            report = inspect(root)
            self.assertTrue(report["local_sources"]["global_ibtracs"]["available"])
            self.assertFalse(report["all_dataset_marts_published"])

    @patch("scripts.operations.objective2_readiness.subprocess.run")
    def test_root_account_is_rejected_without_leaking_identity(self, execute):
        execute.return_value = CompletedProcess([], 0, '{"Arn":"arn:aws:iam::000000000000:root"}', "")
        result = check_aws("marineverse", "ap-south-1")
        self.assertFalse(result["ready"])
        self.assertNotIn("000000000000", json.dumps(result))

    @patch("scripts.operations.objective2_readiness.subprocess.run")
    def test_expected_iam_user_is_accepted(self, execute):
        execute.return_value = CompletedProcess([], 0, '{"Arn":"arn:aws:iam::000000000000:user/marineverse-data-engineer"}', "")
        self.assertTrue(check_aws("marineverse", "ap-south-1")["ready"])

    def test_secret_scanner_redacts_value(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "bad.py"
            secret = "AKIA" + "Q" * 16
            p.write_text("token = '" + secret + "'")
            result = findings([p])
            self.assertTrue(result)
            self.assertNotIn(secret, "\n".join(result))


if __name__ == "__main__":
    unittest.main()
