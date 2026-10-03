import unittest
from unittest.mock import patch

from model import (
    ModelUnavailableError,
    _human_count,
    count_parameters,
    load_model,
    resolve_device,
)


class FakeParameter:
    def __init__(self, count: int, requires_grad: bool = True) -> None:
        self._count = count
        self._requires_grad = requires_grad

    def numel(self) -> int:
        return self._count

    @property
    def requires_grad(self) -> bool:
        return self._requires_grad


class FakeModel:
    def __init__(self) -> None:
        self._params = [FakeParameter(1000), FakeParameter(2000, requires_grad=False)]

    def parameters(self):
        return self._params


class HumanCountTests(unittest.TestCase):
    def test_billions(self) -> None:
        self.assertEqual(_human_count(1_234_000_000), "1.23B")

    def test_millions(self) -> None:
        self.assertEqual(_human_count(456_700_000), "456.7M")

    def test_thousands(self) -> None:
        self.assertEqual(_human_count(12_345), "12.3K")

    def test_small(self) -> None:
        self.assertEqual(_human_count(42), "42")


class RequireTorchTests(unittest.TestCase):
    def test_require_torch_reports_missing_dependencies(self) -> None:
        with patch("model.importlib.import_module", side_effect=ImportError("no torch")):
            with self.assertRaises(ModelUnavailableError) as context:
                from model import require_torch

                require_torch()
            self.assertIn("model", str(context.exception).lower())

    def test_resolve_device_requires_torch(self) -> None:
        with patch("model.importlib.import_module", side_effect=ImportError("no torch")):
            with self.assertRaises(ModelUnavailableError):
                resolve_device(None)


class LoadModelTests(unittest.TestCase):
    def test_load_model_rejects_missing_path(self) -> None:
        with self.assertRaises(ModelUnavailableError):
            load_model("C:/definitely/not/a/model/dir")

    def test_load_model_rejects_file_path(self) -> None:
        with patch("model.require_torch", side_effect=ModelUnavailableError("no torch")):
            with self.assertRaises(ModelUnavailableError):
                # A file (not a dir) must fail before touching torch.
                import tempfile

                with tempfile.NamedTemporaryFile(delete=False) as handle:
                    name = handle.name
                try:
                    load_model(name)
                finally:
                    import os

                    os.unlink(name)


class CountParametersTests(unittest.TestCase):
    def test_counts_total_and_trainable(self) -> None:
        with patch("model.require_torch", return_value=(None, None)):
            result = count_parameters(FakeModel())
        self.assertEqual(result["total"], 3000)
        self.assertEqual(result["trainable"], 1000)
        self.assertEqual(result["total_human"], "3.0K")


if __name__ == "__main__":
    unittest.main()
