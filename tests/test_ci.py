# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

MODULE = Path(__file__).resolve().parents[1] / "scripts/ci.py"
spec = importlib.util.spec_from_file_location("ci", MODULE)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class BuildRulesTest(unittest.TestCase):
    def test_periodic_check_keeps_build_identity_and_only_records_after_28_days(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            built = datetime(2026, 10, 1, tzinfo=timezone.utc)
            state = {"built_at": built.isoformat(), "upstream_sha": "a" * 40, "apk_sha256": "b" * 64}
            (root / "last-build.json").write_text(json.dumps(state))
            self.assertFalse(ci.record_check(root, built + timedelta(days=27)))
            self.assertTrue(ci.record_check(root, built + timedelta(days=28)))
            result = json.loads((root / "last-build.json").read_text())
            self.assertEqual({key: result[key] for key in state}, state)
            self.assertFalse(ci.record_check(root, built + timedelta(days=29)))

    def test_success_record_skips_unchanged_build_but_not_upstream_or_patch_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "patches").mkdir()
            patch = root / "patches/no-audio-ducking.patch"
            patch.write_text("patch v1")
            sha = "a" * 40
            self.assertTrue(ci.needs_build(root, sha))
            (root / "last-build.json").write_text(json.dumps({"upstream_sha": sha, "inputs_hash": ci.inputs_hash(root)}))
            self.assertFalse(ci.needs_build(root, sha))
            self.assertTrue(ci.needs_build(root, sha, force=True))
            self.assertTrue(ci.needs_build(root, "b" * 40))
            (root / "README.md").write_text("说明更新不会影响 APK")
            self.assertFalse(ci.needs_build(root, sha))
            patch.write_text("patch v2")
            self.assertTrue(ci.needs_build(root, sha))

    def test_focus_request_cannot_pass_release_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            player = root / ci.PLAYER
            player.parent.mkdir(parents=True)
            valid = "continuation.ensureActive(); start(); it.release(); mediaPlayer?.stop()"
            player.write_text(valid)
            ci.verify_player(root)
            player.write_text(valid + "\nrequestAudioFocus()")
            with self.assertRaisesRegex(RuntimeError, "音频焦点"):
                ci.verify_player(root)


if __name__ == "__main__":
    unittest.main()
