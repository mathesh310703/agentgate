"""Layer 1 detector: Llama Prompt Guard 2 (22M), a small classifier for prompt injections and jailbreaks.

The gate never decides from the score alone. The score is stored on each untrusted record and used by
one rule (gate.py: recipients taken only from a sender or owner field) and in block explanations.

    scorer = PromptGuard()          # loads nothing until the first score() call
    scorer("some tool output")      # -> malicious probability in [0, 1]

Runs on CPU by default. The model is gated on Hugging Face: HF_TOKEN is read from .env and never printed.
Inputs longer than 512 tokens are split into chunks and the maximum chunk score is returned.
Scores are cached in memory by a hash of the text.
"""

import hashlib
import os
from pathlib import Path

MODEL_ID = "meta-llama/Llama-Prompt-Guard-2-22M"
MODEL_86M = "meta-llama/Llama-Prompt-Guard-2-86M"   # optional larger model (eval/LAYER1_86M.md), off by default
MAX_TOKENS = 512
ROOT = Path(__file__).resolve().parent.parent


class PromptGuard:
    def __init__(self, model_id: str = MODEL_ID, max_tokens: int = MAX_TOKENS, batch_size: int = 16, device: str = "cpu"):
        self.model_id = model_id
        self.device = device
        self.max_tokens = max_tokens
        self.batch_size = batch_size
        self._tok = self._model = None
        self._malicious = None   # label index of the malicious class
        self.cache = {}

    def _load(self):
        if self._model is not None:
            return
        from dotenv import load_dotenv
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        load_dotenv(ROOT / ".env")
        token = os.environ.get("HF_TOKEN") or None
        self._tok = AutoTokenizer.from_pretrained(self.model_id, token=token)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_id, token=token)
        self._model.to(self.device).eval()
        labels = {i: str(n).lower() for i, n in self._model.config.id2label.items()}
        self._malicious = next((i for i, n in labels.items() if "malicious" in n or "injection" in n), 1)

    def chunks(self, text: str) -> list:
        """Split into pieces of at most max_tokens tokens, special tokens included."""
        self._load()
        room = self.max_tokens - self._tok.num_special_tokens_to_add()
        ids = self._tok(text, add_special_tokens=False)["input_ids"]
        return [self._tok.decode(ids[i:i + room]) for i in range(0, len(ids), room)] or [""]

    def score(self, text) -> float:
        text = "" if text is None else str(text)
        if not text.strip():
            return 0.0
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if key not in self.cache:
            self.cache[key] = max(self._score_batch(self.chunks(text)))
        return self.cache[key]

    __call__ = score

    def _score_batch(self, pieces: list) -> list:
        import torch

        out = []
        for i in range(0, len(pieces), self.batch_size):
            enc = self._tok(pieces[i:i + self.batch_size], return_tensors="pt", padding=True, truncation=True,
                            max_length=self.max_tokens)
            if self.device != "cpu":
                enc = enc.to(self.device)
            with torch.no_grad():
                probs = torch.softmax(self._model(**enc).logits, dim=-1)[:, self._malicious]
            out += [float(p) for p in probs]
        return out
