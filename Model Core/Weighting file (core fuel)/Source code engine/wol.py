"""WOL（Wake-on-LAN）工具模块。

职责边界（重要，避免误用）：
- 本模块提供"魔术包构造 / 发送 / 本机网卡 WOL 诊断"三个能力。
- 注意：当电脑处于关机（S5）状态时，后端服务本身已停止，调用方无法通过
  HTTP 触达本模块。真正的"关机→开机"唤醒路径是：同一局域网内的设备
  直接向目标 MAC 广播魔术包（手机 WOL App / 托管设备），与本模块无关。
- 本模块在后端存活时用于：①诊断并返回本机 WOL 支持情况（前端展示指引）；
  ②向指定目标（默认本机有线网卡）发送魔术包，验证发送路径 / 支持
  "睡眠唤醒（WoWLAN）"等场景；③未来"托管常开设备"上的代理可通过
  此端点唤醒工作电脑。
"""

from __future__ import annotations

import re
import socket
import subprocess
from typing import Any, Optional

_WOL_REG_KEY_PREFIX = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"


def normalize_mac(mac: str) -> bytes:
    """把常见 MAC 写法归一为 6 字节：
    '50-5A-65-04-4C-99' / '50:5A:65:04:4C:99' / '505A65044C99'。
    非法输入抛 ValueError。
    """
    hexs = re.sub(r"[^0-9a-fA-F]", "", (mac or "").strip())
    if len(hexs) != 12:
        raise ValueError(f"无效 MAC 地址: {mac!r}")
    return bytes.fromhex(hexs)


def build_magic_packet(mac: str) -> bytes:
    """构造 WOL 魔术包：6 字节 0xFF + 目标 MAC 重复 16 次（共 102 字节）。"""
    mac_bytes = normalize_mac(mac)
    return b"\xff" * 6 + mac_bytes * 16


def send_wake(
    mac: str,
    target: str = "255.255.255.255",
    port: int = 9,
    timeout: float = 2.0,
) -> dict[str, Any]:
    """通过 UDP 广播发送魔术包。

    target 默认全网广播（255.255.255.255）；同一子网内也可填目标主机 IP。
    返回结构化结果，不抛异常（发送失败以 error 字段返回）。
    """
    packet = build_magic_packet(mac)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        sent = sock.sendto(packet, (target, port))
        return {
            "sent": True,
            "bytes": int(sent),
            "target": target,
            "port": int(port),
            "mac": mac,
        }
    except OSError as exc:
        return {
            "sent": False,
            "error": str(exc),
            "target": target,
            "port": int(port),
            "mac": mac,
        }
    finally:
        sock.close()


def _registry_adapter_entries() -> dict[str, dict[str, Any]]:
    """读注册表网卡类枚举：NetCfgInstanceId -> DriverDesc / WOL 相关值。

    Windows 专用；非 Windows 返回空 dict（诊断将如实标注 unsupported）。
    """
    if __import__("os").name != "nt":
        return {}
    import winreg  # noqa: PLC0415

    entries: dict[str, dict[str, Any]] = {}
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, _WOL_REG_KEY_PREFIX
        ) as base:
            index = 0
            while True:
                try:
                    sub_key_name = winreg.EnumKey(base, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        f"{_WOL_REG_KEY_PREFIX}\\{sub_key_name}",
                    ) as key:
                        driver_desc = ""
                        instance_id = ""
                        try:
                            driver_desc, _ = winreg.QueryValueEx(key, "DriverDesc")
                        except OSError:
                            pass
                        try:
                            instance_id, _ = winreg.QueryValueEx(
                                key, "NetCfgInstanceId"
                            )
                        except OSError:
                            pass
                        if not instance_id or not driver_desc:
                            continue
                        flags: Optional[int] = None
                        wake_magic: Optional[int] = None
                        try:
                            flags, _ = winreg.QueryValueEx(key, "PnPCapabilities")
                            flags = int(flags)
                        except OSError:
                            pass
                        try:
                            wake_magic, _ = winreg.QueryValueEx(
                                key, "WakeOnMagicPacket"
                            )
                            wake_magic = int(wake_magic)
                        except OSError:
                            pass
                        entries[instance_id] = {
                            "driver_desc": driver_desc,
                            "pnp_capabilities": flags,
                            "wake_on_magic_packet": wake_magic,
                        }
                except OSError:
                    continue
    except OSError:
        return {}
    return entries


def _adapter_rows() -> list[dict[str, Any]]:
    """通过 `getmac /fo csv /v` 枚举物理网卡（连接名 / 适配器描述 / MAC）。

    纯 subprocess + CSV 解析（快，无 PowerShell 冷启动）；解析失败返回空。
    """
    try:
        output = subprocess.run(
            ["getmac", "/fo", "csv", "/v"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    if not lines:
        return []
    header = [h.strip().strip('"') for h in lines[0].split(",")]

    def col_index(*names: str) -> Optional[int]:
        for name in names:
            try:
                return header.index(name)
            except ValueError:
                continue
        return None

    name_idx = col_index("连接名", "Connection Name")
    mac_idx = col_index("物理地址", "Physical Address")
    desc_idx = col_index("网络适配器", "Network Adapter", "Adapter")
    if name_idx is None or mac_idx is None:
        return []
    for ln in lines[1:]:
        # getmac CSV 字段不含内嵌逗号，按逗号切分剥引号即可
        parts = [p.strip().strip('"') for p in ln.split(",")]
        if len(parts) <= max(name_idx, mac_idx):
            continue
        name, mac = parts[name_idx], parts[mac_idx]
        if not mac or mac in ("", "N/A"):
            continue
        desc = parts[desc_idx] if desc_idx is not None and len(parts) > desc_idx else ""
        # 过滤虚拟/蓝牙/回环适配器：它们不参与真实 WOL 唤醒，避免误判有线支持
        if any(
            token in desc
            for token in ("VMware", "Virtual", "Bluetooth", "Loopback", "TAP", "Tunnel")
        ):
            continue
        rows.append(
            {
                "name": name,
                "description": desc,
                "mac": mac,
            }
        )
    return rows


# 诊断结果缓存（30 秒 TTL）：getmac/注册表查询一次后短时复用，避免高频接口卡顿。
_DIAG_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_DIAG_TTL = 30.0


def diagnose_wol(*, _fresh: bool = False) -> dict[str, Any]:
    """本机 WOL 支持诊断（结果缓存 30 秒；`_fresh=True` 强制重查）。

    返回：
    - adapters: 物理网卡列表（名称/描述/MAC、有线/无线、WOL 注册表标志）
    - wired_wol_ready: 是否存在可支持关机唤醒的有线网卡
    - wifi_wo_wlan: 是否存在无线网卡（其 WOL 通常仅睡眠唤醒）
    - hints: 面向用户的落地指引（中文）
    """
    now = __import__("time").time()
    if not _fresh and _DIAG_CACHE["data"] is not None and now - _DIAG_CACHE["ts"] < _DIAG_TTL:
        return _DIAG_CACHE["data"]

    rows = _adapter_rows()
    reg = _registry_adapter_entries()

    def reg_for(desc: str) -> dict[str, Any]:
        for entry in reg.values():
            if desc and entry.get("driver_desc") == desc:
                return entry
        return {}

    enriched: list[dict[str, Any]] = []
    for ad in rows:
        entry = reg_for(ad.get("description", ""))
        is_wireless = "Wireless" in str(ad.get("description", "")) or "802.11" in str(
            ad.get("description", "")
        )
        enriched.append(
            {
                "name": ad.get("name", ""),
                "description": ad.get("description", ""),
                "mac": ad.get("mac", ""),
                "is_wireless": is_wireless,
                "wake_on_magic_packet_reg": entry.get("wake_on_magic_packet"),
                "pnp_capabilities": entry.get("pnp_capabilities"),
            }
        )

    wired = [a for a in enriched if not a["is_wireless"]]
    wireless = [a for a in enriched if a["is_wireless"]]
    wired_wol_ready = any(
        a.get("wake_on_magic_packet_reg") is not None
        and int(a["wake_on_magic_packet_reg"]) != 0
        for a in wired
    ) or bool(wired)

    hints: list[str] = []
    if wired:
        hints.append(
            "发现有线网卡：插入网线 + BIOS 开启 Wake-on-LAN + 设备管理器"
            "「允许此设备唤醒计算机」后，支持关机（S5）魔术包唤醒。"
        )
    else:
        hints.append("未发现有线网卡：关机唤醒需有线网卡支持，或改用智能插座/ESP32 物理开机方案。")
    if wireless:
        hints.append(
            "Wi-Fi（WoWLAN）通常仅支持电脑睡眠状态下唤醒，关机状态不可靠；"
            "同一 AP 与驱动需配合。"
        )
    if not wired and not wireless:
        hints.append("未枚举到物理网卡（可能权限或环境受限），请以设备管理器实际配置为准。")

    data = {
        "adapters": enriched,
        "wired_wol_ready": wired_wol_ready,
        "wifi_wo_wlan": bool(wireless),
        "hints": hints,
        "os": "windows" if __import__("os").name == "nt" else "other",
    }
    _DIAG_CACHE["ts"] = now
    _DIAG_CACHE["data"] = data
    return data


def pick_default_target_mac() -> Optional[str]:
    """挑选默认唤醒目标：优先有线网卡 MAC，其次无线。无则 None。"""
    diag = diagnose_wol()
    for ad in diag["adapters"]:
        if not ad["is_wireless"] and ad.get("mac"):
            return ad["mac"]
    for ad in diag["adapters"]:
        if ad.get("mac"):
            return ad["mac"]
    return None
