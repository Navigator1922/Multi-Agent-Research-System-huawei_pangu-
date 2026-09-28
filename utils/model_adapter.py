import os
from typing import Optional
from openai import OpenAI
import openai

class UniversalModel:
    """通用大语言模型调用接口。"""

    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> None:
        if not api_key:
            raise ValueError("必须提供 API Key。如果是本地免密环境，可随意填入非空字符串（如 'EMPTY'）。")
            
        self.model_name = model_name
        self.max_tokens = int(max_tokens)
        if self.max_tokens <= 0:
            raise ValueError("max_tokens 必须大于 0")

        # 初始化标准客户端。传入 base_url 即可重定向到任何本地或私有云节点
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def generate(self, prompt: str, do_sample: bool = True, temperature: float = 0.7) -> str:
        """向模型发送单轮对话请求并返回生成的文本，内置防截断校验。"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=temperature if do_sample else 0.0,
                # 当不需要采样时，使用极低的温度值模拟贪心解码
            )
        except openai.APIConnectionError as exc:
            raise RuntimeError(f"模型服务连接失败，请检查网络或 base_url 配置：{exc}") from exc
        except openai.APIError as exc:
            raise RuntimeError(f"模型 API 调用报错：{exc}") from exc

        choice = response.choices[0]
        
        # 截断硬阻断逻辑：利用 API 原生的 finish_reason 精准判定
        if choice.finish_reason == "length":
            raise BufferError(
                f"生成内容达到最大长度限制 ({self.max_tokens} tokens) 被强制截断，"
                "请在环境中调大 LLM_MAX_TOKENS 或缩短证据输入。"
            )

        content = choice.message.content
        if not content:
            raise ValueError("模型返回了空的内容")
            
        return content.strip()


def load_model_from_environment() -> Optional[UniversalModel]:
    """读取环境变量以初始化通用模型适配器。

    未配置模型名称时返回 ``None``，便于系统在无模型状态下进行代码骨架测试。
    """

    model_name = os.getenv("LLM_MODEL_NAME", "").strip()
    if not model_name:
        return None

    api_key = os.getenv("LLM_API_KEY", "EMPTY").strip()
    # base_url 是切换云端商业模型和本地测试模型的关键
    base_url = os.getenv("LLM_BASE_URL", "").strip() or None
    token_limit = os.getenv("LLM_MAX_TOKENS", "2048").strip()

    try:
        max_tokens = int(token_limit)
    except ValueError as exc:
        raise ValueError("LLM_MAX_TOKENS 必须是整数") from exc

    return UniversalModel(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        max_tokens=max_tokens,
    )


__all__ = ["UniversalModel", "load_model_from_environment"]