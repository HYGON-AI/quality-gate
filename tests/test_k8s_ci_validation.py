# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("validation", pathlib.Path(__file__).parents[1] / "scripts/k8s-ci-validation.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class ValidationTests(unittest.TestCase):
    def test_all_manifests_isolated_bounded(self):
        for mode in v.MODES:
            m = v.manifest("test", "token", 2, mode)
            p = m["spec"]["tasks"][0]["template"]["spec"]
            self.assertEqual(p["nodeSelector"], {"kubernetes.io/hostname": "github-nmz3"})
            self.assertFalse(p["automountServiceAccountToken"])
            self.assertLessEqual(p["activeDeadlineSeconds"], 300)
            self.assertNotIn("volumes", p)
            self.assertIn("@sha256:", p["containers"][0]["image"])

    def test_no_arbitrary_card_count(self):
        for cards in (0, -1, 9, 24):
            with self.assertRaises(ValueError):
                v.manifest("test", "token", cards, "success")

    def test_success_requires_exit_and_marker(self):
        good = [{"status": {"containerStatuses": [{"state": {"terminated": {"exitCode": 0}}}]}}]
        self.assertTrue(v.verdict("Completed", good, "COMPUTE_PASSED"))
        self.assertFalse(v.verdict("Running", good, "COMPUTE_PASSED"))
        self.assertFalse(v.verdict("Completed", [], "COMPUTE_PASSED"))
        self.assertFalse(v.verdict("Completed", good, ""))
        self.assertFalse(v.verdict("Aborted", good, "COMPUTE_PASSED"))
        good[0]["status"]["containerStatuses"][0]["state"]["terminated"]["exitCode"] = 17
        self.assertFalse(v.verdict("Completed", good, "COMPUTE_PASSED"))

    def test_delete_checks_uid_and_label(self):
        obj = {"metadata": {"name": "mine", "namespace": v.NS, "uid": "uid1", "labels": {v.LABEL: "token"}}}
        with patch.object(v, "read", return_value=obj), patch.object(v, "kube") as k:
            v.delete_owned({"name": "mine", "uid": "uid1"}, "token")
            self.assertEqual(k.call_args.kwargs["data"]["preconditions"], {"uid": "uid1"})
            k.reset_mock()
            for rec, token in (({"name": "mine", "uid": "other"}, "token"), ({"name": "mine", "uid": "uid1"}, "other")):
                with self.assertRaises(RuntimeError):
                    v.delete_owned(rec, token)
            k.assert_not_called()

    def test_missing_is_not_permission_error(self):
        with patch.object(v, "read", return_value=None), patch.object(v, "kube") as k:
            v.delete_owned({"name": "mine"}, "token")
            k.assert_not_called()
        with patch.object(v, "read", side_effect=RuntimeError("Forbidden")):
            with self.assertRaises(RuntimeError):
                v.delete_owned({"name": "mine"}, "token")

    def test_cleanup_api_failure_not_success(self):
        with tempfile.TemporaryDirectory() as d:
            x = v.Experiment(d, "success")
            with patch.object(v, "read", side_effect=RuntimeError("API unavailable")):
                with self.assertRaises(RuntimeError):
                    x.cleanup()
            self.assertNotIn("cleanup", x.state)

    def test_wait_deadline(self):
        with tempfile.TemporaryDirectory() as d:
            x = v.Experiment(d, "success")
            with self.assertRaises(TimeoutError):
                x.wait([], timeout=-1)

    def test_secrets_redacted(self):
        self.assertNotIn("abcdef", v.sanitize("Bearer abcdef github_pat_abcdef"))

    def test_parallel_requires_running_and_distinct_uuid(self):
        pod = [{"status": {"phase": "Running"}}]
        a = 'DEVICE_REPORT={"count":1,"devices":[{"uuid":"a"}]}\nCOMPUTE_READY'
        b = a.replace('"a"', '"b"')
        self.assertTrue(v.isolated_pair([("Running", pod, a), ("Running", pod, b)]))
        self.assertFalse(v.isolated_pair([("Running", pod, a), ("Running", pod, a)]))
        self.assertFalse(v.isolated_pair([("Completed", pod, a), ("Running", pod, b)]))
        self.assertFalse(v.isolated_pair([("Running", [], a), ("Running", pod, b)]))

    def test_device_evidence_must_be_complete(self):
        for logs in ('', 'DEVICE_REPORT={"count":2,"devices":[{"uuid":"a"}]}',
                     'DEVICE_REPORT={"count":2,"devices":[{"uuid":"a"},{"uuid":"a"}]}'):
            with self.assertRaises(RuntimeError):
                v.device_ids(logs, 2)

    def test_cancellation_raises_not_success(self):
        with self.assertRaises(KeyboardInterrupt):
            v.interrupted(2, None)

    def test_queue_requires_scheduler_resource_reason(self):
        self.assertTrue(v.resource_wait_evidence([{"reason": "FailedScheduling", "message": "Insufficient hygon.com/hcu"}]))
        self.assertFalse(v.resource_wait_evidence([]))
        self.assertFalse(v.resource_wait_evidence([{"reason": "Failed", "message": "ImagePullBackOff"}]))
        self.assertFalse(v.resource_wait_evidence([{"reason": "Scheduled", "message": "Pod assigned"}]))


if __name__ == "__main__":
    unittest.main()
