"""Pure current-consumer controls; no SDK, provider, process or source acceptance grant."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import procurement_artifact_transport_consumer as transport

class ArtifactTransportConsumerControls(unittest.TestCase):
    def setUp(self):
        self.source = (Path(__file__).resolve().parents[1] / transport.WORKFLOW).read_bytes()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / transport.WORKFLOW
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(self.source)
        self.blob = mock.Mock(return_value=transport.CURRENT_BLOB)
        self.git = mock.Mock(return_value=(transport.CURRENT_BLOB + "\n").encode())

    def binding(self, historical=None):
        return transport.current_workflow_binding(self.root, transport.WORKFLOW,
            transport.PREVIOUS_BLOB if historical is None else historical, self.blob, self.git)

    def test_actual_current_source_reconstructs_exact_historical_blob(self):
        previous = transport.reconstruct_predecessor(self.source)
        self.assertEqual(len(previous), 52974)
        self.assertEqual(transport.git_blob(previous), "133875aa827a87ebcfdc775a63d2702fb3846c4d")
        self.assertEqual(hashlib.sha256(previous).hexdigest(), "1fcc17194f91991d573eaecd2f372aad56346737e16fcae07792d63c0b0bfddd")

    def test_reviewed_current_working_and_head_are_admitted(self):
        self.assertEqual(self.binding(), transport.CURRENT_BLOB)
        self.blob.assert_called_once_with(self.root, transport.WORKFLOW)
        self.git.assert_called_once_with(self.root, "rev-parse", "HEAD:" + transport.WORKFLOW)

    def test_other_paths_are_not_enrolled(self):
        self.assertEqual(transport.current_workflow_binding(self.root, "other.cs", "original", self.blob, self.git), "original")
        self.blob.assert_not_called()
        self.git.assert_not_called()

    def test_historical_binding_cannot_be_refreshed(self):
        with self.assertRaises(ValueError):
            self.binding(transport.CURRENT_BLOB)

    def test_wrong_historical_binding_is_refused(self):
        with self.assertRaises(ValueError):
            self.binding("0" * 40)

    def test_stale_workflow_is_refused(self):
        self.target.write_bytes(transport.reconstruct_predecessor(self.source))
        with self.assertRaises(ValueError):
            self.binding()

    def test_undeclared_workflow_change_is_refused(self):
        self.target.write_bytes(self.source.replace(b"timeout-minutes", b"timeout_minute", 1))
        with self.assertRaises(ValueError):
            self.binding()

    def test_partial_action_upgrade_is_refused(self):
        self.target.write_bytes(self.source.replace(b"cf430e030ddbb5b0abf93d22962f4752f3646cd9", b"ea165f8d65b6e75b540449e92b4886f43607fa02", 1))
        with self.assertRaises(ValueError):
            self.binding()

    def test_changed_current_working_blob_is_refused(self):
        self.blob.return_value = transport.PREVIOUS_BLOB
        with self.assertRaises(ValueError):
            self.binding()

    def test_working_head_divergence_is_refused(self):
        self.git.return_value = (transport.PREVIOUS_BLOB + "\n").encode()
        with self.assertRaises(ValueError):
            self.binding()

    def test_oversized_source_is_refused(self):
        self.target.write_bytes(self.source + b"\n")
        with self.assertRaises(ValueError):
            self.binding()

    def test_symlink_source_is_refused(self):
        with mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ValueError):
                self.binding()

    def test_changed_inverse_is_refused(self):
        with mock.patch.object(transport, "INVERSE_EDITS", transport.INVERSE_EDITS[:-1]):
            with self.assertRaises(ValueError):
                self.binding()

    def test_untyped_source_is_refused(self):
        with self.assertRaises(ValueError):
            transport.reconstruct_predecessor(self.source.decode())

if __name__ == "__main__":
    unittest.main()
