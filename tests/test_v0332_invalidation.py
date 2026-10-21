"""v0.33.2 I1: an acceptance does not outlive the product it was decided on."""
import inspect
import unittest

from sumcp import evidence, iterate, stack


def _manifest(**status):
    m = {"dataset_id": "t", "capabilities": {}, "history": []}
    for name, st in status.items():
        evidence.set_capability(m, name.replace("_", ".", 1), st, {"output": f"{name}.su"}, "test", "run0",
                                artifact=f"{name}.su")
    return m


class Invalidation(unittest.TestCase):
    def test_new_stack_returns_migration_and_depth_to_unknown(self):
        m = _manifest(stack_completed="PASS", migration_completed="PASS", depth_completed="PASS")
        changed = evidence.invalidate_downstream(m, "stack.completed", "the stack was recomputed", "test", "run1")
        self.assertEqual(changed, ["migration.completed", "depth.completed"])
        for name in changed:
            cap = m["capabilities"][name]
            self.assertEqual(cap["status"], "UNKNOWN")
            self.assertEqual(cap["evidence"]["previous_status"], "PASS")
            self.assertEqual(cap["evidence"]["invalidated_by"], "stack.completed")
            self.assertTrue(cap["evidence"]["previous_artifact"])
        self.assertEqual(m["capabilities"]["stack.completed"]["status"], "PASS")

    def test_new_nmo_returns_stack_and_images_to_unknown(self):
        m = _manifest(nmo_applied="PASS", stack_completed="PASS", migration_completed="FAIL")
        changed = evidence.invalidate_downstream(m, "nmo.applied", "the NMO correction was recomputed", "t", "r")
        self.assertEqual(changed, ["stack.completed", "migration.completed"])

    def test_absent_or_unknown_capabilities_are_left_alone(self):
        m = _manifest(stack_completed="PASS", migration_completed="UNKNOWN")
        self.assertEqual(evidence.invalidate_downstream(m, "stack.completed", "x", "t", "r"), [])
        self.assertNotIn("depth.completed", m["capabilities"])

    def test_attempt_history_survives(self):
        m = _manifest(stack_completed="PASS", migration_completed="PASS")
        m["capabilities"]["migration.completed"]["attempts"] = [{"run_id": "a", "released": True}]
        evidence.invalidate_downstream(m, "stack.completed", "x", "t", "r")
        self.assertEqual(len(m["capabilities"]["migration.completed"]["attempts"]), 1)

    def test_unknown_origin_is_refused(self):
        with self.assertRaises(evidence.DatasetError):
            evidence.invalidate_downstream(_manifest(), "geometry.cmp_assigned", "x", "t", "r")

    def test_downstream_steps_refuse_after_invalidation(self):
        m = _manifest(stack_completed="PASS", migration_completed="PASS")
        evidence.invalidate_downstream(m, "stack.completed", "x", "t", "r")
        with self.assertRaises(Exception):
            evidence.require(m, ["migration.completed"], "depth conversion")

    def test_artifacts_are_marked_and_depth_convert_checks_the_mark(self):
        m = _manifest(stack_completed="PASS", migration_completed="PASS", depth_completed="PASS")
        m["artifacts"] = {"migration_phase_shift_smooth": {"path": "a.su"}, "depth_depth_convert": {"path": "b.su"},
                          "migration_phase_shift_rejected": {"path": "c.su"}, "stack": {"path": "s.su"}}
        self.assertIsNone(evidence.superseded(m, "migration_phase_shift_smooth"))
        evidence.invalidate_downstream(m, "stack.completed", "the stack was recomputed", "t", "r9")
        self.assertEqual(evidence.superseded(m, "migration_phase_shift_smooth")["run_id"], "r9")
        self.assertTrue(evidence.superseded(m, "depth_depth_convert"))
        self.assertIsNone(evidence.superseded(m, "migration_phase_shift_rejected"))
        self.assertIsNone(evidence.superseded(m, "stack"))
        from sumcp import depth
        self.assertIn('evidence.superseded(manifest, "migration_phase_shift_smooth")', inspect.getsource(depth))

    def test_new_time_migration_withdraws_depth_convert_only(self):
        m = _manifest(migration_completed="PASS")
        evidence.set_capability(m, "depth.completed", "PASS", {"method": "depth_convert"}, "t", "r0",
                                artifact="d.su")
        m["artifacts"] = {"depth_depth_convert": {"path": "d.su"}, "depth_depth_pspi": {"path": "p.su"}}
        changed = evidence.invalidate_after_migration(m, "the time migration was recomputed", "t", "r2")
        self.assertEqual(changed, ["depth_depth_convert", "depth.completed"])
        cap = m["capabilities"]["depth.completed"]
        self.assertEqual(cap["status"], "UNKNOWN")
        self.assertEqual(cap["evidence"]["invalidated_by"], "migration.completed")
        self.assertTrue(evidence.superseded(m, "depth_depth_convert"))
        self.assertIsNone(evidence.superseded(m, "depth_depth_pspi"))
        self.assertEqual(m["capabilities"]["migration.completed"]["status"], "PASS")

    def test_new_time_migration_leaves_depth_pspi_alone(self):
        m = _manifest(migration_completed="PASS")
        evidence.set_capability(m, "depth.completed", "PASS", {"method": "depth_pspi"}, "t", "r0", artifact="p.su")
        m["artifacts"] = {"depth_depth_pspi": {"path": "p.su"}}
        self.assertEqual(evidence.invalidate_after_migration(m, "x", "t", "r"), [])
        self.assertEqual(m["capabilities"]["depth.completed"]["status"], "PASS")

    def test_released_migration_calls_the_depth_withdrawal(self):
        from sumcp import migrate
        src = inspect.getsource(migrate)
        i = src.index("evidence.invalidate_after_migration(")
        self.assertLess(i, src.index('evidence.record_product_run(manifest, "migration.completed"'))
        self.assertIn("if release:", src[i - 200:i])

    def test_every_recomputation_site_invalidates(self):
        src = inspect.getsource(stack)
        for reason in ("the velocity model was recomputed", "the NMO correction was recomputed",
                       "the stack was recomputed"):
            self.assertIn(reason, src)
        src = inspect.getsource(iterate)
        for reason in ("the CMP gathers were conditioned", "the velocity model was refined"):
            self.assertIn(f'"stack.completed", "{reason}"', src.replace("\n", " ").replace("  ", ""))


if __name__ == "__main__":
    unittest.main()
