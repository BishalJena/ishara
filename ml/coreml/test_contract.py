"""Core ML input contract; the parity test needs the local model and artifacts."""
import unittest

import numpy as np

import contract


def frames(count: int) -> np.ndarray:
    return np.random.default_rng(count).normal(size=(count, contract.FEATURE_DIM)).astype(np.float32)


class PadContract(unittest.TestCase):
    def test_shapes_and_dtypes_are_exact(self):
        features, mask = contract.pad(frames(10))
        self.assertEqual(features.shape, (1, 256, 609))
        self.assertEqual(mask.shape, (1, 256))
        self.assertEqual((features.dtype, mask.dtype), (np.float32, np.float32))

    def test_real_frames_copied_and_tail_zero_padded(self):
        source = frames(37)
        features, mask = contract.pad(source)
        np.testing.assert_array_equal(features[0, :37], source)
        self.assertFalse(features[0, 37:].any())
        np.testing.assert_array_equal(mask[0], np.r_[np.ones(37), np.zeros(219)])

    def test_full_length_clip_is_all_real(self):
        features, mask = contract.pad(frames(256))
        np.testing.assert_array_equal(mask, np.ones((1, 256), dtype=np.float32))
        np.testing.assert_array_equal(features[0], frames(256))

    def test_long_clip_rejected_not_truncated(self):
        with self.assertRaisesRegex(ValueError, "257 frames exceeds"):
            contract.pad(frames(257))

    def test_minimum_frames_match_pytorch_pipeline(self):
        self.assertEqual(contract.pad(frames(4))[1].sum(), 4)
        with self.assertRaises(ValueError):
            contract.pad(frames(3))

    def test_wrong_width_or_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            contract.pad(np.zeros((10, 608), dtype=np.float32))
        with self.assertRaises(ValueError):
            contract.pad(np.zeros((1, 10, 609), dtype=np.float32))
        bad = frames(10)
        bad[3, 5] = np.nan
        with self.assertRaises(ValueError):
            contract.pad(bad)

    def test_cosine_ignores_scale_and_rejects_zero(self):
        self.assertAlmostEqual(contract.cosine([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertAlmostEqual(contract.cosine([1, 0], [0, 1]), 0.0)
        with self.assertRaises(ValueError):
            contract.cosine([0, 0], [1, 0])


if __name__ == "__main__":
    unittest.main()
