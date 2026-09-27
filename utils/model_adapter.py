"""openPangu 的可选模型适配器。

本地运行没有设置模型路径时不会导入 torch 或 transformers；
云端运行时通过 PANGU_MODEL_PATH 加载已经存在的模型目录。
"""

import os
import sys
from pathlib import Path
from typing import Any, Optional


class PanguModel:
    """使用 Transformers 加载并调用 openPangu 因果语言模型。"""

    def __init__(
        self,
        model_path: str,
        device: str = "auto",
        max_new_tokens: int = 1024,
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
        self.last_generation_hit_limit = False

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
        self._configure_attention_backend()
        self.model.to(self.device)
        self.model.eval()

    def _configure_attention_backend(self) -> None:
        """关闭当前云端不兼容的融合 attention，改用模型自带的 eager 实现。

        openPangu 的自定义模型代码会在导入时根据 Ascend 设备自动把
        ``NPU_ATTN_INFR`` 设为 ``True``。当前云端的融合算子在实际生成时
        会报 ``aclnnFusedInferAttentionOnScoreV3`` 错误，而且把模型移动到
        CPU 后仍会错误调用 NPU 算子。模型源码同时提供了
        ``eager_attention_forward`` 分支，因此在适配层关闭这个全局开关，
        不需要修改 Hugging Face 缓存中的模型文件。

        如需在已验证兼容的 CANN 环境中恢复融合算子，可设置
        ``PANGU_USE_FUSED_ATTN=1``；默认关闭是为了保证当前课程环境能够
        完成推理。
        """

        use_fused = os.getenv("PANGU_USE_FUSED_ATTN", "0").strip().lower()
        use_fused = use_fused in {"1", "true", "yes", "on"}

        # CPU 没有 torch_npu 融合算子，任何情况下都必须使用普通实现。
        if self.device != "npu" or not use_fused:
            patched = False
            for module_name, module in list(sys.modules.items()):
                if module_name.endswith("modeling_openpangu_dense"):
                    if hasattr(module, "NPU_ATTN_INFR"):
                        module.NPU_ATTN_INFR = False
                        patched = True

            # 自定义模型的 attention 层读取同一个 config 对象；显式指定
            # eager，避免关闭融合算子后又被 Transformers 选择到其他后端。
            configs = [getattr(self.model, "config", None)]
            decoder = getattr(self.model, "model", None)
            configs.append(getattr(decoder, "config", None))
            for config in configs:
                if config is None:
                    continue
                if hasattr(config, "_attn_implementation"):
                    config._attn_implementation = "eager"
                if hasattr(config, "_attn_implementation_internal"):
                    config._attn_implementation_internal = "eager"

            if self.device == "npu" and not patched:
                raise RuntimeError(
                    "未找到 openPangu 的 modeling_openpangu_dense 模块，"
                    "无法关闭 NPU 融合 attention"
                )

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

        try:
            with self._torch.no_grad():
                output = self.model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=False,
                    pad_token_id=getattr(self.tokenizer, "pad_token_id", None),
                )
        except Exception as exc:
            raise RuntimeError(
                f"盘古模型推理失败，device={self.device}，"
                f"attention={'fused' if self._fused_attention_enabled else 'eager'}，"
                f"原始异常={type(exc).__name__}: {exc}"
            ) from exc

        prompt_length = inputs["input_ids"].shape[-1]
        generated_tokens = output[0][prompt_length:]
        self.last_generation_hit_limit = (
            int(generated_tokens.shape[-1]) >= self.max_new_tokens
        )
        return self.tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True,
        ).strip()

    @property
    def _fused_attention_enabled(self) -> bool:
        """返回当前模型模块是否仍启用了 NPU 融合 attention。"""

        for module_name, module in sys.modules.items():
            if module_name.endswith("modeling_openpangu_dense"):
                return bool(getattr(module, "NPU_ATTN_INFR", False))
        return False


def load_model_from_environment() -> Optional[PanguModel]:
    """读取环境变量，未配置模型路径时返回 ``None``。"""

    model_path = os.getenv("PANGU_MODEL_PATH", "").strip()
    if not model_path:
        return None

    device = os.getenv("PANGU_DEVICE", "auto").strip() or "auto"
    token_limit = os.getenv("PANGU_MAX_NEW_TOKENS", "1024").strip()
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
