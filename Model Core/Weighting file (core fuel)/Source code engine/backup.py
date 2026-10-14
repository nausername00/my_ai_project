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
