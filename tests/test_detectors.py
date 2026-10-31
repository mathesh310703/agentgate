"""Offline tests for agentgate/detectors.py: chunking, max over chunks and the cache, with a fake
tokenizer and model (no download, no HF_TOKEN). Run: `.venv\Scripts\python tests/test_detectors.py`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentgate.detectors import PromptGuard  # noqa: E402


class FakeTok:
    """One token per word; 2 special tokens per sequence, like DeBERTa's [CLS] ... [SEP]."""

    def num_special_tokens_to_add(self):
        return 2

    def __call__(self, text, add_special_tokens=True):
        return {"input_ids": text.split()}

    def decode(self, ids):
        return " ".join(ids)


class FakeGuard(PromptGuard):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.seen = []

    def _load(self):
        self._tok = FakeTok()

    def _score_batch(self, pieces):
        self.seen += pieces
        return [0.9 if "assistant" in p else 0.1 for p in pieces]


def test_long_input_is_chunked_and_max_is_taken():
    g = FakeGuard(max_tokens=6)                       # 4 words per chunk
    text = "a b c d e f g h assistant j"
    assert g.chunks(text) == ["a b c d", "e f g h", "assistant j"]
    assert g.score(text) == 0.9


def test_scores_are_cached_by_text():
    g = FakeGuard(max_tokens=512)
    assert g.score("hello there") == 0.1 and g.score("hello there") == 0.1
    assert g.seen == ["hello there"] and len(g.cache) == 1


def test_empty_text_scores_zero_without_loading():
    g = FakeGuard()
    assert g.score("") == 0.0 and g.score(None) == 0.0 and g.seen == []


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
