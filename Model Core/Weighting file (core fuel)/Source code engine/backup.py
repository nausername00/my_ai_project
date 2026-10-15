"""角色数据一键备份（12 层第 8 层基础设施的最轻形态）。

把墨灵的核心数据——长期记忆（memory.json）、情绪状态（affect*.json）、
隐私设置（privacy.json，如存在）、角色卡（characters/）与演出规则
（performance_rules.json，作为角色演出配置）——快照到 Backups/character/<时间戳>/。

范围克制：不备份大体积资产目录（assets/、Live2D 模型、立绘、视频输出），
只保护"身份与记忆"这类文本数据；备份按时间戳建目录，重复备份不互相覆盖。
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

_DEFAULT_DATA_FILES = ("memory.json", "affect*.json", "privacy.json")
_DEFAULT_DATA_DIRS = ("characters",)


def backup_character_data(
    character_root: str | Path,
    backup_root: str | Path,
    extra_files: list[str] | None = None,
) -> dict[str, Any]:
    """把 Character 根下的数据文件快照到备份根/<时间戳>/；返回备份信息。

    - character_root: 角色数据根（Character/）。
    - backup_root: 备份根（Backups/character/）。
    - extra_files: 额外备份的相对路径（如 Docs & Compliance/performance_rules.json）。
    - 备份的文件以相对路径记录；一个文件都没备份到时抛 ValueError。
    """
    source = Path(character_root)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = Path(backup_root) / timestamp
    target.mkdir(parents=True, exist_ok=False)

    copied: list[str] = []
    for pattern in _DEFAULT_DATA_FILES:
        for item in sorted(source.glob(pattern)):
            if item.is_file():
                shutil.copy2(item, target / item.name)
                copied.append(item.name)
    for directory in _DEFAULT_DATA_DIRS:
        directory_path = source / directory
        if directory_path.is_dir():
            shutil.copytree(directory_path, target / directory)
            copied.append(directory + "/")
    for relative in extra_files or []:
        item = Path(relative)
        if (source / item).is_file():
            destination = target / item.parent
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / item, destination / item.name)
            copied.append(str(item).replace("\\", "/"))

    if not copied:
        shutil.rmtree(target, ignore_errors=True)
        raise ValueError("角色数据目录中没有可备份的数据文件")

    return {
        "backup_dir": str(target),
        "files": sorted(copied),
        "count": len(copied),
        "created_at": timestamp,
    }


# ---------------------------------------------------------------------------
# 阶段 0：完整性校验 / 恢复预览 / 恢复（拒绝覆盖）/ 保留策略
# ---------------------------------------------------------------------------


def verify_backup(backup_dir: str | Path) -> dict[str, Any]:
    """校验一份备份：文件存在、非空、JSON 可解析；返回逐文件报告。"""
    root = Path(backup_dir)
    if not root.is_dir():
        raise ValueError(f"备份目录不存在: {backup_dir}")
    errors: list[str] = []
    checked: list[str] = []
    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(root).as_posix()
        checked.append(relative)
        try:
            if item.stat().st_size < 1:
                errors.append(f"{relative}: 文件为空")
                continue
            if item.suffix.lower() == ".json":
                import json as _json

                with item.open("r", encoding="utf-8") as handle:
                    _json.load(handle)
        except (OSError, ValueError) as error:
            errors.append(f"{relative}: {error}")
    return {
        "backup_dir": str(root),
        "ok": not errors,
        "checked": checked,
        "count": len(checked),
        "errors": errors,
    }


def restore_preview(backup_dir: str | Path, target_root: str | Path) -> dict[str, Any]:
    """列出恢复将产生的相对路径与目标绝对路径；不执行任何写入。"""
    root = Path(backup_dir)
    target = Path(target_root).resolve()
    if not root.is_dir():
        raise ValueError(f"备份目录不存在: {backup_dir}")
    entries = []
    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(root)
        entries.append(
            {
                "source": item.as_posix(),
                "relative": relative.as_posix(),
                "target": (target / relative).as_posix(),
            }
        )
    return {"backup_dir": str(root), "target_root": str(target), "entries": entries}


def restore_backup(
    backup_dir: str | Path,
    target_root: str | Path,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """把备份恢复到 target_root；绝不覆盖已存在文件（冲突时拒绝写入）。

    dry_run=True 时只做检查与冲突探测，不写入任何文件。
    返回 {restored, conflicts, dry_run}；有冲突时不写任何冲突文件，其余照写。
    """
    preview = restore_preview(backup_dir, target_root)
    target = Path(target_root)
    restored: list[str] = []
    conflicts: list[str] = []
    for entry in preview["entries"]:
        destination = Path(entry["target"])
        if destination.exists():
            conflicts.append(entry["relative"])
            continue
        if dry_run:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry["source"], destination)
        restored.append(entry["relative"])
    return {
        "backup_dir": str(target),
        "dry_run": bool(dry_run),
        "restored": sorted(restored),
        "conflicts": sorted(conflicts),
        "restored_count": len(restored),
        "conflict_count": len(conflicts),
    }


def prune_backups(backup_root: str | Path, keep_last: int = 10) -> dict[str, Any]:
    """保留最近 keep_last 份时间戳备份，删除更旧目录；返回删除清单。"""
    root = Path(backup_root)
    if not root.is_dir():
        return {"removed": [], "kept": []}
    directories = sorted(
        (d for d in root.iterdir() if d.is_dir()),
        key=lambda d: d.name,
        reverse=True,
    )
    keep = max(1, int(keep_last))
    to_remove = directories[keep:]
    removed = []
    for directory in to_remove:
        try:
            shutil.rmtree(directory, ignore_errors=True)
            removed.append(directory.name)
        except OSError:
            continue
    return {
        "backup_root": str(root),
        "removed": sorted(removed),
        "kept": sorted(d.name for d in directories[:keep]),
        "keep_last": keep,
    }
