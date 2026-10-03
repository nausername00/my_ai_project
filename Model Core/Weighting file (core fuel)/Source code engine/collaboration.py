"""Local multi-agent collaboration for design and engineering review."""

from dataclasses import dataclass
import json
from time import perf_counter
from typing import Any

from inference import GenerationRequest, InferenceEngine, ModelUnavailableError


@dataclass(frozen=True)
class Collaborator:
    key: str
    name: str
    focus: str
    instruction: str


COLLABORATORS = (
    Collaborator(
        "architecture",
        "架构伙伴",
        "系统布局、模块边界和可持续扩展",
        "检查模块边界、数据流、状态管理、权限边界和长期可维护性。",
    ),
    Collaborator(
        "code",
        "代码伙伴",
        "实现可行性、类型安全和异常处理",
        "寻找实现漏洞、边界条件、重复逻辑、错误处理和可测试的最小改动。",
    ),
    Collaborator(
        "ui",
        "界面伙伴",
        "交互流程、信息层级和可理解性",
        "检查用户流程、界面布局、状态反馈、可访问性和是否会让用户误解角色行为。",
    ),
    Collaborator(
        "testing",
        "测试伙伴",
        "验收标准、回归风险和验证方案",
        "提出可复现的验收标准、测试用例、失败场景和最小验证命令。",
    ),
)
MAX_ROLE_INSTRUCTION_LENGTH = 1200
MAX_SYNTHESIS_ITEMS = 12


def list_collaborator_roles() -> list[dict[str, str]]:
    return [
        {
            "key": collaborator.key,
            "name": collaborator.name,
            "focus": collaborator.focus,
            "instruction": collaborator.instruction,
        }
        for collaborator in COLLABORATORS
    ]


def resolve_collaborators(role_configs: Any) -> list[Collaborator]:
    if role_configs is None:
        return list(COLLABORATORS)
    if not isinstance(role_configs, list) or not role_configs:
        raise ValueError("roles must be a non-empty array")

    registry = {collaborator.key: collaborator for collaborator in COLLABORATORS}
    resolved = []
    seen = set()
    for config in role_configs:
        if (
            not isinstance(config, dict)
            or set(config) - {"key", "enabled", "instruction"}
            or config.get("key") not in registry
            or not isinstance(config.get("enabled"), bool)
            or not isinstance(config.get("instruction"), str)
        ):
            raise ValueError("collaborator role configuration is invalid")
        key = config["key"]
        instruction = config["instruction"].strip()
        if key in seen:
            raise ValueError("collaborator roles must be unique")
        seen.add(key)
        if len(instruction) > MAX_ROLE_INSTRUCTION_LENGTH:
            raise ValueError("collaborator instruction exceeds its length limit")
        if config["enabled"]:
            original = registry[key]
            resolved.append(
                Collaborator(
                    key=original.key,
                    name=original.name,
                    focus=original.focus,
                    instruction=instruction or original.instruction,
                )
            )
    if not resolved:
        raise ValueError("at least one collaborator role must be enabled")
    return resolved


def _validate_synthesis(raw: str) -> dict[str, list[str]]:
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"综合结果不是有效 JSON：{error}") from error
    if not isinstance(result, dict):
        raise ValueError("综合结果必须是 JSON 对象")

    validated: dict[str, list[str]] = {}
    for field in ("consensus", "prioritized", "conflicts", "next_steps"):
        items = result.get(field)
        if (
            not isinstance(items, list)
            or len(items) > MAX_SYNTHESIS_ITEMS
            or any(
                not isinstance(item, str) or not item.strip() or len(item) > 700
                for item in items
            )
        ):
            raise ValueError(f"综合结果字段 {field} 格式无效")
        unique_items = []
        seen_items = set()
        for item in items:
            normalized = " ".join(item.casefold().split())
            if normalized not in seen_items:
                seen_items.add(normalized)
                unique_items.append(item.strip())
        validated[field] = unique_items
    return validated


def is_local_engine(engine: InferenceEngine) -> bool:
    backend = getattr(engine, "backend", None)
    endpoint = getattr(backend, "endpoint", None)
    if endpoint is None:
        return True
    from urllib.parse import urlsplit

    return urlsplit(endpoint).hostname in {"localhost", "127.0.0.1", "::1"}


def run_collaboration(
    engine: InferenceEngine,
    system_prompt: str,
    task: str,
    role_configs: Any = None,
) -> dict[str, Any]:
    """Run enabled local review roles and produce a traceable synthesis."""
    if not is_local_engine(engine):
        raise ValueError("协作智能体只允许使用本机模型服务")
    collaborators = resolve_collaborators(role_configs)
    opinions: list[dict[str, Any]] = []
    for collaborator in collaborators:
        started_at = perf_counter()
        request = GenerationRequest(
            prompt=(
                "这是一个本地协作评审任务。你不是墨灵本人，而是她的协作伙伴。"
                "请只提供可核验、可执行的建议，不要声称已修改文件或完成测试。"
                f"\n你的角色：{collaborator.name}，关注：{collaborator.focus}。"
                f"\n评审要求：{collaborator.instruction}"
                f"\n任务：\n{task}"
            ),
            max_tokens=420,
            system_prompt=(
                system_prompt
                + "\n你是协作小组成员。不要执行文件、网络、联系人或系统操作。"
            ),
        )
        try:
            response = engine.generate(request).strip()
            if not response:
                raise ModelUnavailableError("模型返回了空评审意见")
            opinions.append(
                {
                    "agent": collaborator.key,
                    "name": collaborator.name,
                    "focus": collaborator.focus,
                    "response": response,
                    "status": "completed",
                    "model": engine.model_name,
                    "source": "local",
                    "duration_ms": round((perf_counter() - started_at) * 1000),
                    "error": "",
                }
            )
        except ModelUnavailableError as error:
            opinions.append(
                {
                    "agent": collaborator.key,
                    "name": collaborator.name,
                    "focus": collaborator.focus,
                    "response": "",
                    "status": "failed",
                    "model": engine.model_name,
                    "source": "local",
                    "duration_ms": round((perf_counter() - started_at) * 1000),
                    "error": str(error),
                }
            )

    synthesis = None
    synthesis_error = ""
    successful_opinions = [item for item in opinions if item["status"] == "completed"]
    if successful_opinions:
        dossier = "\n\n".join(
            f"【{item['name']}｜{item['focus']}】\n{item['response']}"
            for item in successful_opinions
        )
        missing = [
            f"{item['name']}（{item['error']}）"
            for item in opinions
            if item["status"] == "failed"
        ]
        synthesis_prompt = (
            "你是墨灵，负责综合本次角色评审。只根据收到的意见总结，不伪造缺失角色的意见。"
            "合并重复建议并按影响/风险/紧迫度排序；明确记录互相矛盾或证据不足的判断。"
            "只输出 JSON，不要 Markdown，字段必须是 consensus、prioritized、conflicts、next_steps，"
            "每个字段为字符串数组；没有内容时返回空数组。不要声称已修改代码或完成测试。"
            f"\n原任务：\n{task}\n\n本次未能完成的角色：\n{json.dumps(missing, ensure_ascii=False)}"
            f"\n\n已完成角色的原始意见：\n{dossier}"
        )
        for attempt in range(2):
            prompt = synthesis_prompt
            if attempt:
                prompt = (
                    "上一次综合结果未通过结构校验，原因："
                    f"{synthesis_error}。请重新综合，并严格只输出一个 JSON 对象。"
                    "必须包含 consensus、prioritized、conflicts、next_steps 四个字段，"
                    "每个字段都是字符串数组；没有内容时使用空数组。"
                    '格式示例：{"consensus":["结论"],"prioritized":["优先事项"],'
                    '"conflicts":[],"next_steps":["下一步"]}。'
                    "\n\n"
                    + synthesis_prompt
                )
            try:
                raw_synthesis = engine.generate(
                    GenerationRequest(
                        prompt=prompt,
                        max_tokens=900,
                        system_prompt=system_prompt + "\n这是本地协作总结，不执行外部操作。",
                        json_mode=True,
                        temperature=0.0,
                    )
                ).strip()
                synthesis = _validate_synthesis(raw_synthesis)
                synthesis_error = ""
                break
            except ModelUnavailableError as error:
                synthesis_error = str(error)
                break
            except ValueError as error:
                synthesis_error = str(error)
    return {
        "model": engine.model_name,
        "lead": "moling",
        "collaborators": opinions,
        "synthesis": synthesis,
        "synthesis_error": synthesis_error,
    }
