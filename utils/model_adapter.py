"""openPangu 的可选模型适配器。

本地运行没有设置模型路径时不会导入 torch 或 transformers；
云端运行时通过 PANGU_MODEL_PATH 加载已经存在的模型目录。
"""

import os
from pathlib import Path
from typing import Any, Optional


class PanguModel:
    """使用 Transformers 加载并调用 openPangu 因果语言模型。"""

    def __init__(
        self,
        model_path: str,
        device: str = "auto",
        max_new_tokens: int = 512,
    ) -> None:
        if not Path(model_path).is_dir():
            raise FileNotFoundError(f"盘古模型目录不存在：{model_path}")

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "云端模型模式需要安装 torch 和 transformers"
            ) from exc

        self._torch = torch
        self.device = self._choose_device(torch, device)
        self.max_new_tokens = int(max_new_tokens)
        if self.max_new_tokens <= 0:
            raise ValueError("max_new_tokens 必须大于 0")

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            trust_remote_code=True,
        )
        if getattr(self.tokenizer, "pad_token_id", None) is None:
            eos_token_id = getattr(self.tokenizer, "eos_token_id", None)
            if eos_token_id is not None:
                self.tokenizer.pad_token_id = eos_token_id

        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
        )
        self.model.to(self.device)
        self.model.eval()

    @staticmethod
    def _choose_device(torch: Any, requested: str) -> str:
        """根据配置和当前机器能力选择 CPU、CUDA 或 Ascend NPU。"""

        if requested != "auto":
            return requested

        # 某些 CANN 环境需要先导入 torch_npu，才能注册 torch.npu。
        try:
            import torch_npu
        except ImportError:
            pass

        npu = getattr(torch, "npu", None)
        if npu is not None and npu.is_available():
            return "npu"
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def generate(self, prompt: str) -> str:
        """根据提示词生成文本，并移除输入提示词本身。"""

        prompt_text = prompt
        apply_chat_template = getattr(self.tokenizer, "apply_chat_template", None)
        if callable(apply_chat_template):
            try:
                prompt_text = apply_chat_template(
                    [{"role": "user", "content": prompt}],
                    tokenize=False,
                    add_generation_prompt=True,
                )
            except (TypeError, ValueError):
                # 某些模型没有可用的聊天模板，退回普通文本提示。
                prompt_text = prompt

        inputs = self.tokenizer(prompt_text, return_tensors="pt")
        inputs = {
            key: value.to(self.device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }

        with self._torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=getattr(self.tokenizer, "pad_token_id", None),
            )

        prompt_length = inputs["input_ids"].shape[-1]
        generated_tokens = output[0][prompt_length:]
        return self.tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True,
        ).strip()


def load_model_from_environment() -> Optional[PanguModel]:
    """读取环境变量，未配置模型路径时返回 ``None``。"""

    model_path = os.getenv("PANGU_MODEL_PATH", "").strip()
    if not model_path:
        return None

    device = os.getenv("PANGU_DEVICE", "auto").strip() or "auto"
    token_limit = os.getenv("PANGU_MAX_NEW_TOKENS", "512").strip()
    try:
        max_new_tokens = int(token_limit)
    except ValueError as exc:
        raise ValueError("PANGU_MAX_NEW_TOKENS 必须是整数") from exc

    return PanguModel(
        model_path=model_path,
        device=device,
        max_new_tokens=max_new_tokens,
    )


__all__ = ["PanguModel", "load_model_from_environment"]
