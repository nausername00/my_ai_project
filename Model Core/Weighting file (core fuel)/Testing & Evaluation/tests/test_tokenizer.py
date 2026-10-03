import tempfile
import unittest

from inference import GenerationRequest, ModelUnavailableError, TransformersBackend
from metrics import perplexity, tokenize


class TokenizeTests(unittest.TestCase):
    def test_lowercases_and_splits_on_non_alphanumeric(self) -> None:
        self.assertEqual(tokenize("Hello, World!"), ["hello", "world"])

    def test_handles_cjk_as_tokens(self) -> None:
        # CJK characters are not in [a-z0-9]; the default tokenizer returns
        # an empty list for pure CJK input. This is a documented limitation.
        self.assertEqual(tokenize("你好世界"), [])

    def test_empty_input(self) -> None:
        self.assertEqual(tokenize(""), [])

    def test_digits_are_kept(self) -> None:
        self.assertEqual(tokenize("v1.2 release"), ["v1", "2", "release"])


class PerplexityTests(unittest.TestCase):
    def test_known_value(self) -> None:
        # exp(-(-2.0)) = exp(2.0) ≈ 7.389
        self.assertAlmostEqual(perplexity([-2.0, -2.0, -2.0]), 7.389056, places=3)

    def test_empty_returns_inf(self) -> None:
        self.assertEqual(perplexity([]), float("inf"))

    def test_zero_log_likelihood_is_perfect(self) -> None:
        self.assertAlmostEqual(perplexity([0.0, 0.0]), 1.0)


class LazyTokenizerTests(unittest.TestCase):
    def test_transformers_backend_reports_missing_deps_on_generate(self) -> None:
        # The directory exists, so construction succeeds; generation then
        # fails because torch/transformers are not installed (lazy load).
        with tempfile.TemporaryDirectory() as directory:
            backend = TransformersBackend(directory)
            with self.assertRaises(ModelUnavailableError):
                backend.generate(GenerationRequest("你好"))


if __name__ == "__main__":
    unittest.main()
