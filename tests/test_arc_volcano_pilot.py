import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("pilot", Path(__file__).parents[1] / "scripts/arc-volcano-pilot.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class PilotTest(unittest.TestCase):
    def test_cpu_only_and_isolated(self):
        m = pilot.manifest("probe", "owner", 0)
        p = m["spec"]["tasks"][0]["template"]["spec"]
        self.assertFalse(p["automountServiceAccountToken"])
        self.assertNotIn("volumes", p)
        self.assertTrue(p["securityContext"]["runAsNonRoot"])
        self.assertEqual(p["activeDeadlineSeconds"], 120)
        self.assertEqual(m["spec"]["maxRetry"], 0)
        self.assertNotIn("plugins", m["spec"])
        for kind in ("requests", "limits"):
            self.assertEqual(set(p["containers"][0]["resources"][kind]), {"cpu", "memory"})

    def test_both_fixed_commands_are_valid_python(self):
        for code in (0, 17):
            m = pilot.manifest("probe", "owner", code)
            cmd = m["spec"]["tasks"][0]["template"]["spec"]["containers"][0]["command"]
            compile(cmd[2], "probe", "exec")
            self.assertIn("sys.exit(%d)" % code, cmd[2])
        with self.assertRaises(ValueError):
            pilot.manifest("probe", "owner", 99)

    def test_cleanup_identity(self):
        obj = {"metadata": {"name": "probe", "namespace": pilot.NS, "uid": "uid1",
                            "labels": {pilot.LABEL: "owner"}}}
        self.assertTrue(pilot.is_owned(obj, "probe", "owner", "uid1"))
        for args in [("other", "owner", "uid1"), ("probe", "other", "uid1"), ("probe", "owner", "uid2")]:
            self.assertFalse(pilot.is_owned(obj, *args))


if __name__ == "__main__":
    unittest.main()
