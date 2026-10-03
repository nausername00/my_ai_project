"""Inference backends for the local AI service.

The service remains runnable without ML dependencies, while a real
Transformers model can be enabled through environment variables.
"""

from dataclasses import dataclass
import base64
import importlib
import json
import os
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    max_tokens: int = 128
    system_prompt: str = ""
    history: tuple[tuple[str, str], ...] = ()
    json_mode: bool = False
    temperature: float | None = None


class ModelUnavailableError(RuntimeError):
    """Raised when a configured model cannot be loaded or used."""


class InferenceBackend(Protocol):
    model_name: str

    def generate(self, request: GenerationRequest, *, image: bytes | None = None) -> str:
        ...


class PlaceholderBackend:
    model_name = "placeholder"

    def generate(self, request: GenerationRequest, *, image: bytes | None = None) -> str:
        if image is not None:
            raise ModelUnavailableError("placeholder backend does not support image input")
        return f"[{self.model_name}] {request.prompt}"[: request.max_tokens]


class OllamaBackend:
    """Local Ollama chat API backend using only the Python standard library."""

    def __init__(self, model_name: str, base_url: str, timeout: float = 120.0) -> None:
        if not model_name.strip():
            raise ModelUnavailableError("OLLAMA_MODEL is required")
        if not base_url.startswith(("http://", "https://")):
            raise ModelUnavailableError("OLLAMA_URL must start with http:// or https://")
        self.model_name = model_name.strip()
        self.endpoint = base_url.rstrip("/") + "/api/chat"
        self.timeout = timeout

    def generate(
        self,
        request: GenerationRequest,
        *,
        image: bytes | None = None,
    ) -> str:
        if image is not None:
            if not image:
                raise ValueError("image must not be empty")
            if len(image) > 10 * 1024 * 1024:
                raise ValueError("image exceeds the 10 MB analysis limit")
            host = urlsplit(self.endpoint).hostname
            if host not in {"localhost", "127.0.0.1", "::1"}:
                raise ModelUnavailableError(
                    "image analysis is restricted to a loopback Ollama service"
                )
        payload = {
            "model": self.model_name,
            "messages": [
                *(
                    [{"role": "system", "content": request.system_prompt}]
                    if request.system_prompt
                    else []
                ),
                *(
                    {"role": role, "content": content}
                    for role, content in request.history
                ),
                {
                    "role": "user",
                    "content": request.prompt,
                    **({"images": [base64.b64encode(image).decode("ascii")]} if image is not None else {}),
                },
            ],
            "stream": False,
            "options": {"num_predict": request.max_tokens},
        }
        if request.json_mode:
            payload["format"] = "json"
        if request.temperature is not None:
            payload["options"]["temperature"] = request.temperature
        http_request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace").strip()
            raise ModelUnavailableError(
                f"Ollama returned HTTP {error.code}"
                + (f": {details}" if details else "")
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ModelUnavailableError(f"cannot reach Ollama at {self.endpoint}: {error}") from error
        except (UnicodeDecodeError, ValueError) as error:
            raise ModelUnavailableError(f"Ollama returned invalid JSON: {error}") from error

        if not isinstance(result, dict):
            raise ModelUnavailableError("Ollama response must be a JSON object")
        message = result.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ModelUnavailableError("Ollama response did not contain message.content")
        return content


class TransformersBackend:
    """Lazy-loading Hugging Face Transformers backend."""

    def __init__(self, model_path: str) -> None:
        path = Path(model_path).expanduser()
        if not path.exists():
            raise ModelUnavailableError(f"model path does not exist: {path}")
        if not path.is_dir():
            raise ModelUnavailableError(f"model path must be a directory: {path}")
        self.model_path = path
        self.model_name = path.name
        self._tokenizer: Any = None
        self._model: Any = None
        self._torch: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            transformers = importlib.import_module("transformers")
            self._torch = importlib.import_module("torch")
        except ImportError as error:
            raise ModelUnavailableError(
                "transformers and torch are required; install the 'model' extra"
            ) from error
        try:
            self._tokenizer = transformers.AutoTokenizer.from_pretrained(
                str(self.model_path)
            )
            self._model = transformers.AutoModelForCausalLM.from_pretrained(
                str(self.model_path)
            )
            self._model.eval()
        except (OSError, ValueError, RuntimeError) as error:
            raise ModelUnavailableError(f"failed to load model: {error}") from error

    def generate(self, request: GenerationRequest, *, image: bytes | None = None) -> str:
        if image is not None:
            raise ModelUnavailableError(
                "the configured Transformers backend does not support image input"
            )
        self._load()
        try:
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.extend(
                {"role": role, "content": content}
                for role, content in request.history
            )
            messages.append({"role": "user", "content": request.prompt})
            if hasattr(self._tokenizer, "apply_chat_template"):
                inputs = self._tokenizer.apply_chat_template(
                    messages,
                    add_generation_prompt=True,
                    return_tensors="pt",
                    tokenize=True,
                )
                if hasattr(inputs, "input_ids"):
                    input_ids = inputs.input_ids
                    model_inputs = dict(inputs)
                else:
                    input_ids = inputs
                    model_inputs = {"input_ids": inputs}
            else:
                rendered_prompt = ""
                if request.system_prompt:
                    rendered_prompt += f"System: {request.system_prompt}\n\n"
                for role, content in request.history:
                    speaker = "Assistant" if role == "assistant" else "User"
                    rendered_prompt += f"{speaker}: {content}\n"
                rendered_prompt += f"User: {request.prompt}\nAssistant:"
                encoded = self._tokenizer(rendered_prompt, return_tensors="pt")
                input_ids = encoded["input_ids"]
                model_inputs = dict(encoded)
            output = self._model.generate(
                **model_inputs,
                max_new_tokens=request.max_tokens,
                do_sample=False,
            )
            return self._tokenizer.decode(
                output[0][input_ids.shape[-1] :],
                skip_special_tokens=True,
            )
        except (RuntimeError, ValueError, TypeError) as error:
            raise ModelUnavailableError(f"model generation failed: {error}") from error


class CloudAPIHTTPSBackend:
    """OpenAI-compatible HTTPS inference backend (stdlib-only urllib).

    Any API provider that speaks the ``POST /v1/chat/completions`` format
    works out of the box (OpenAI, Azure, DeepSeek, Qwen, Groq, SiliconFlow,
    OpenRouter, …).  The default state is *disabled* — users must set both
    ``CLOUD_API_BASE_URL`` and ``CLOUD_API_KEY`` via the environment *and*
    opt in to ``MODEL_BACKEND=cloud`` before any remote call is made.

    No telemetry, no external connections outside the configured base URL,
    no disk logging of prompts or responses.
    """

    def __init__(
        self,
        model_name: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 180.0,
        organisation: str | None = None,
        project: str | None = None,
    ) -> None:
        env_model = os.getenv("CLOUD_API_MODEL", "").strip()
        env_base = os.getenv("CLOUD_API_BASE_URL", "").strip()
        env_key = os.getenv("CLOUD_API_KEY", "").strip()
        model = (model_name or env_model).strip()
        base = (base_url or env_base).rstrip("/")
        key = api_key if api_key is not None else env_key
        if not model:
            raise ModelUnavailableError(
                "CloudAPIHTTPSBackend: missing model_name; set CLOUD_API_MODEL or pass model_name="
            )
        if not base:
            raise ModelUnavailableError(
                "CloudAPIHTTPSBackend disabled: set CLOUD_API_BASE_URL to enable remote endpoints."
            )
        if not base.startswith(("http://", "https://")):
            raise ModelUnavailableError("CLOUD_API_BASE_URL must start with http:// or https://")
        if not base.startswith("https://"):
            # Local-only private networks over http are still OK as long as
            # they are loopback / site-local, but never for public internet.
            host = urlsplit(base).hostname or ""
            safe = host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local")
            if not safe:
                raise ModelUnavailableError(
                    "CloudAPIHTTPSBackend requires https:// for non-localhost base URLs."
                )
        if not key:
            raise ModelUnavailableError(
                "CloudAPIHTTPSBackend disabled: CLOUD_API_KEY is required; "
                "远程云端推理默认关闭，以避免未授权的外网调用。"
            )
        self.model_name = model
        self.endpoint = base + "/v1/chat/completions"
        self._api_key = str(key)
        self._organisation = organisation or os.getenv("CLOUD_API_ORG", "").strip() or None
        self._project = project or os.getenv("CLOUD_API_PROJECT", "").strip() or None
        self.timeout = float(timeout)

    def generate(self, request: GenerationRequest, *, image: bytes | None = None) -> str:
        if image is not None:
            raise ModelUnavailableError(
                "remote image analysis is disabled; use a loopback Ollama vision model"
            )
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        for role, content in request.history:
            if role not in {"user", "assistant"}:
                continue
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": request.prompt})
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "max_tokens": int(request.max_tokens),
        }
        if request.temperature is not None:
            payload["temperature"] = float(request.temperature)
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        if self._organisation:
            headers["OpenAI-Organization"] = self._organisation
        if self._project:
            headers["OpenAI-Project"] = self._project
        data = json.dumps(payload).encode("utf-8")
        http_request = Request(
            self.endpoint,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace").strip()
            raise ModelUnavailableError(
                f"CloudAPI returned HTTP {error.code}" + (f": {details[:400]}" if details else "")
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ModelUnavailableError(
                f"CloudAPI 调用失败（{urlsplit(self.endpoint).hostname or 'unknown'}）：{error}"
            ) from error
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, ValueError) as error:
            raise ModelUnavailableError(f"CloudAPI 返回无效 JSON：{error}") from error
        if not isinstance(body, dict):
            raise ModelUnavailableError("CloudAPI 返回不是对象")
        err = body.get("error")
        if isinstance(err, dict):
            raise ModelUnavailableError(
                f"CloudAPI 报错：{err.get('message') or err}"
            )
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelUnavailableError("CloudAPI 返回缺少 choices 字段")
        first = choices[0]
        if not isinstance(first, dict):
            raise ModelUnavailableError("CloudAPI choices[0] 不是对象")
        msg = first.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, str):
            raise ModelUnavailableError("CloudAPI 响应未包含 message.content")
        return content


class InferenceEngine:
    def __init__(self, backend: InferenceBackend | None = None) -> None:
        self.backend = backend or PlaceholderBackend()
        self.model_name = self.backend.model_name

    @classmethod
    def from_environment(cls) -> "InferenceEngine":
        backend_name = os.getenv("MODEL_BACKEND", "placeholder").strip().lower()
        if backend_name == "placeholder":
            return cls()
        if backend_name == "transformers":
            model_path = os.getenv("MODEL_PATH", "").strip()
            if not model_path:
                raise ModelUnavailableError(
                    "MODEL_PATH is required when MODEL_BACKEND=transformers"
                )
            return cls(TransformersBackend(model_path))
        if backend_name == "ollama":
            model_name = os.getenv("OLLAMA_MODEL", "").strip()
            base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").strip()
            return cls(OllamaBackend(model_name, base_url))
        if backend_name == "cloud":
            return cls(CloudAPIHTTPSBackend(""))
        raise ValueError(f"unsupported MODEL_BACKEND: {backend_name}")

    @classmethod
    def list_available_backends(cls) -> list[dict[str, Any]]:
        """Return a small list of backends that can be switched to at
        runtime (used by ``/v1/engine/list``).  Only backends that have
        enough configuration to actually load are marked ``loadable``."""
        backends: list[dict[str, Any]] = []
        backends.append({
            "id": "placeholder",
            "name": "占位后端 (placeholder)",
            "description": "零依赖，仅作连通性测试。",
            "loadable": True,
            "model_name": "placeholder",
        })
        # Ollama
        ollama_model = os.getenv("OLLAMA_MODEL", "").strip()
        ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").strip()
        backends.append({
            "id": "ollama",
            "name": "本地 Ollama",
            "description": "走 /api/chat，需本地已启动 ollama serve。",
            "loadable": bool(ollama_model) and ollama_url.startswith(("http://", "https://")),
            "model_name": ollama_model or "<未设置 OLLAMA_MODEL>",
            "base_url": ollama_url,
        })
        # Transformers
        model_path = os.getenv("MODEL_PATH", "").strip()
        backends.append({
            "id": "transformers",
            "name": "Transformers (本地 torch)",
            "description": "需要安装 [model] extra 并提供 MODEL_PATH。",
            "loadable": bool(model_path) and Path(model_path).expanduser().is_dir(),
            "model_name": Path(model_path).name if model_path else "",
            "model_path": model_path,
        })
        # Cloud
        cloud_model = os.getenv("CLOUD_API_MODEL", "").strip()
        cloud_base = os.getenv("CLOUD_API_BASE_URL", "").strip()
        cloud_key = bool(os.getenv("CLOUD_API_KEY", "").strip())
        backends.append({
            "id": "cloud",
            "name": "云端 OpenAI 兼容协议",
            "description": "需设置 CLOUD_API_BASE_URL + CLOUD_API_KEY + CLOUD_API_MODEL，默认关闭。",
            "loadable": bool(cloud_model and cloud_base and cloud_key and cloud_base.startswith(("http://", "https://"))),
            "model_name": cloud_model or "",
            "base_url": cloud_base or "",
            "key_configured": cloud_key,
        })
        return backends

    def switch_backend(self, backend_id: str, *, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Switch the engine's backend in-place.

        Returns a summary dict with the new ``model_name``, ``kind``, and
        whether the switch happened (``switched``).  Raises
        :class:`ModelUnavailableError` if the requested backend can't be
        loaded with the current environment.
        """
        overrides = dict(overrides or {})
        bid = (backend_id or "").strip().lower()
        if bid == "placeholder":
            self.backend = PlaceholderBackend()
        elif bid == "ollama":
            model = overrides.get("model") or os.getenv("OLLAMA_MODEL", "").strip()
            url = overrides.get("base_url") or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").strip()
            self.backend = OllamaBackend(str(model), str(url))
        elif bid == "transformers":
            mp = overrides.get("model_path") or os.getenv("MODEL_PATH", "").strip()
            if not mp:
                raise ModelUnavailableError("MODEL_PATH 未设置，无法切换到 transformers 后端。")
            self.backend = TransformersBackend(str(mp))
        elif bid == "cloud":
            model = overrides.get("model") or os.getenv("CLOUD_API_MODEL", "").strip()
            base = overrides.get("base_url") or os.getenv("CLOUD_API_BASE_URL", "").strip()
            key = overrides.get("api_key")  # None → keep env; "" → explicitly empty → error
            # Note: callers that want to pass a transient key may do so.
            self.backend = CloudAPIHTTPSBackend(model, base_url=base, api_key=key)
        else:
            raise ValueError(f"未知 backend_id: {backend_id!r}，可选 placeholder/ollama/transformers/cloud。")
        self.model_name = self.backend.model_name
        return {
            "switched": True,
            "backend_id": bid,
            "model_name": self.model_name,
            "kind": type(self.backend).__name__,
        }

    def generate(
        self,
        request: GenerationRequest,
        *,
        image: bytes | None = None,
    ) -> str:
        prompt = request.prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be empty")
        if request.max_tokens < 1 or request.max_tokens > 4096:
            raise ValueError("max_tokens must be between 1 and 4096")
        if image is not None and not isinstance(image, bytes):
            raise TypeError("image must be bytes")
        normalized_request = GenerationRequest(
            prompt=prompt,
            max_tokens=request.max_tokens,
            system_prompt=request.system_prompt,
            history=request.history,
            json_mode=request.json_mode,
            temperature=request.temperature,
        )
        if image is None:
            return self.backend.generate(normalized_request)
        return self.backend.generate(normalized_request, image=image)
