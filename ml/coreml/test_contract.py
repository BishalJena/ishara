"""Core ML input contract; the model tests need the local package and artifacts."""
import importlib.util
import unittest
from pathlib import Path

import numpy as np

import contract

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
PACKAGE = ARTIFACTS / "SignCLIPEncoder.mlpackage"
CHECKPOINT = (Path(__file__).resolve().parents[2] / "spikes" / "recognition" / "artifacts"
              / "signclip" / "baseline_temporal_checkpoint_best.pt")
HAS_COREML = importlib.util.find_spec("coremltools") is not None


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


@unittest.skipUnless(HAS_COREML, "coremltools not installed; use ml/coreml/.venv")
@unittest.skipUnless(PACKAGE.exists(), f"{PACKAGE.name} absent; run convert_signclip.py")
class CoreMLPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import coremltools as ct

        cls.ct = ct
        cls.spec = ct.models.MLModel(str(PACKAGE), skip_model_load=True).get_spec()

    def test_io_matches_swift_contract(self):
        def shapes(features):
            return {f.name: (tuple(f.type.multiArrayType.shape), f.type.multiArrayType.dataType)
                    for f in features}

        float32 = self.ct.proto.FeatureTypes_pb2.ArrayFeatureType.FLOAT32
        self.assertEqual(shapes(self.spec.description.input),
                         {"features": ((1, 256, 609), float32), "mask": ((1, 256), float32)})
        self.assertEqual(shapes(self.spec.description.output), {"embedding": ((1, 768), float32)})
        self.assertEqual(self.spec.WhichOneof("Type"), "mlProgram")
        self.assertEqual(self.spec.description.metadata.userDefined["precision"], "fp16")

    @unittest.skipUnless(CHECKPOINT.exists(), "SignCLIP checkpoint absent; run setup_signclip.py")
    @unittest.skipUnless(any((ARTIFACTS / "features").glob("*.npz")),
                         "no cached clip features; run parity.py once")
    def test_recommended_units_match_pytorch_on_cached_clips(self):
        import convert_signclip as cs

        wrapper, model = cs.load_wrapper()
        cached = sorted((ARTIFACTS / "features").glob("*.npz"))[:5]
        for unit in ("CPU_AND_GPU", "CPU_ONLY"):
            coreml = self.ct.models.MLModel(str(PACKAGE), compute_units=getattr(self.ct.ComputeUnit, unit))
            for path in cached:
                with np.load(path, allow_pickle=False) as saved:
                    features = saved["features"]
                reference = cs.signclip.embed(model, features)
                padded, mask = contract.pad(features)
                output = coreml.predict({"features": padded, "mask": mask})["embedding"][0]
                with self.subTest(unit=unit, clip=path.stem[:12]):
                    self.assertGreaterEqual(contract.cosine(reference, output), 0.999)
                    self.assertGreater(contract.cosine(reference, cs.torch_embed(wrapper, padded, mask)), 0.999999)


if __name__ == "__main__":
    unittest.main()
