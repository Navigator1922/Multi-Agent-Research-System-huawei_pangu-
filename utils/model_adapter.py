"""Optional model adapters.

The orchestration code does not import Transformers directly. Local tests can
use ``MockModel`` or omit a model, while the cloud notebook can inject
``PanguModel`` after its openPangu model path is confirmed.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional


class MockModel:
    """Small deterministic response queue for Agent unit tests."""

    def __init__(self, responses: Optional[Iterable[str]] = None):
        self.responses: List[str] = list(responses or [])

    def generate(self, prompt: str, **_: Any) -> str:
        if self.responses:
            return self.responses.pop(0)
        return ""


class PanguModel:
    """Lazy Transformers adapter for openPangu on the cloud notebook.

    ``torch`` and ``transformers`` are imported only when this adapter is
    instantiated, so the local standard-library pipeline remains runnable.
    """

    def __init__(
        self,
        model_path: str,
        device: str = "auto",
        trust_remote_code: bool = True,
        default_max_new_tokens: int = 512,
    ):
        self.model_path = model_path
        self.device = device
        self.trust_remote_code = trust_remote_code
        self.default_max_new_tokens = default_max_new_tokens
        self.tokenizer: Any = None
        self.model: Any = None
        self._torch: Any = None
        self._load()

    def _load(self) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "PanguModel 需要云端已安装 torch 和 transformers"
            ) from exc

        self._torch = torch
        resolved_device = self._resolve_device(torch)
        self.device = resolved_device
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path,
            trust_remote_code=self.trust_remote_code,
        )
        if getattr(self.tokenizer, "pad_token_id", None) is None:
            eos_token_id = getattr(self.tokenizer, "eos_token_id", None)
            if eos_token_id is not None:
                self.tokenizer.pad_token_id = eos_token_id

        load_kwargs = {"trust_remote_code": self.trust_remote_code}
        if resolved_device == "npu" and hasattr(torch, "float16"):
            load_kwargs["torch_dtype"] = torch.float16
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            **load_kwargs,
        )
        if hasattr(self.model, "to"):
            self.model.to(resolved_device)
        if hasattr(self.model, "eval"):
            self.model.eval()

    def _resolve_device(self, torch: Any) -> str:
        if self.device != "auto":
            return self.device
        npu = getattr(torch, "npu", None)
        if npu is not None and getattr(npu, "is_available", lambda: False)():
            return "npu"
        return "cuda" if getattr(torch.cuda, "is_available", lambda: False)() else "cpu"

    def generate(self, prompt: str, **kwargs: Any) -> str:
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("PanguModel 尚未完成加载")
        max_new_tokens = int(kwargs.get("max_new_tokens", self.default_max_new_tokens))
        inputs = self.tokenizer(prompt, return_tensors="pt")
        inputs = {
            key: value.to(self.device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }
        generation_kwargs = {
            "max_new_tokens": max_new_tokens,
            "do_sample": bool(kwargs.get("do_sample", False)),
        }
        if kwargs.get("temperature") is not None:
            generation_kwargs["temperature"] = float(kwargs["temperature"])
        if kwargs.get("top_p") is not None:
            generation_kwargs["top_p"] = float(kwargs["top_p"])

        with self._torch.no_grad():
            output = self.model.generate(**inputs, **generation_kwargs)
        prompt_length = inputs["input_ids"].shape[-1]
        generated_tokens = output[0][prompt_length:]
        return self.tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()


__all__ = ["MockModel", "PanguModel"]
