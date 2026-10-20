"""WOL（Wake-on-LAN）模块测试：魔术包构造/发送/诊断。

发送路径全部 mock socket，避免测试向真实局域网广播。
"""

import unittest
from unittest import mock

import wol


class NormalizeMacTests(unittest.TestCase):
    def test_hyphen_format(self) -> None:
        self.assertEqual(wol.normalize_mac("50-5A-65-04-4C-99"), bytes.fromhex("505A65044C99"))

    def test_colon_format(self) -> None:
        self.assertEqual(wol.normalize_mac("50:5A:65:04:4C:99"), bytes.fromhex("505A65044C99"))

    def test_plain_hex(self) -> None:
        self.assertEqual(wol.normalize_mac("505A65044C99"), bytes.fromhex("505A65044C99"))

    def test_invalid_raises(self) -> None:
        for bad in ("", "50-5A", "zz-5A-65-04-4C-99", None):
            with self.assertRaises(ValueError):
                wol.normalize_mac(bad)  # type: ignore[arg-type]


class BuildMagicPacketTests(unittest.TestCase):
    def test_packet_shape(self) -> None:
        packet = wol.build_magic_packet("50-5A-65-04-4C-99")
        self.assertEqual(len(packet), 102)
        self.assertEqual(packet[:6], b"\xff" * 6)
        self.assertEqual(packet[6:], bytes.fromhex("505A65044C99") * 16)

    def test_different_mac(self) -> None:
        packet = wol.build_magic_packet("AA:BB:CC:DD:EE:FF")
        self.assertEqual(packet[6:], bytes.fromhex("AABBCCDDEEFF") * 16)


class SendWakeTests(unittest.TestCase):
    def _fake_socket(self):
        fake = mock.Mock()
        fake.sendto.return_value = 102
        return fake

    def test_send_success(self) -> None:
        fake = self._fake_socket()
        with mock.patch("wol.socket.socket", return_value=fake):
            result = wol.send_wake("50-5A-65-04-4C-99")
        self.assertTrue(result["sent"])
        self.assertEqual(result["bytes"], 102)
        self.assertEqual(result["target"], "255.255.255.255")
        self.assertEqual(result["port"], 9)
        fake.sendto.assert_called_once()
        payload = fake.sendto.call_args[0][0]
        self.assertEqual(len(payload), 102)

    def test_send_custom_target_port(self) -> None:
        fake = self._fake_socket()
        with mock.patch("wol.socket.socket", return_value=fake):
            result = wol.send_wake(
                "AA:BB:CC:DD:EE:FF", target="192.168.1.100", port=7
            )
        self.assertTrue(result["sent"])
        self.assertEqual(result["target"], "192.168.1.100")
        self.assertEqual(result["port"], 7)

    def test_send_oserror_reports_failure(self) -> None:
        fake = mock.Mock()
        fake.sendto.side_effect = OSError("network unreachable")
        with mock.patch("wol.socket.socket", return_value=fake):
            result = wol.send_wake("50-5A-65-04-4C-99")
        self.assertFalse(result["sent"])
        self.assertIn("error", result)
        fake.close.assert_called_once()


class DiagnoseTests(unittest.TestCase):
    def setUp(self) -> None:
        wol._DIAG_CACHE["ts"] = 0.0
        wol._DIAG_CACHE["data"] = None

    def test_diagnose_falls_back_gracefully(self) -> None:
        # getmac 无输出 → 空网卡列表 + 兜底 hint
        with mock.patch("wol.subprocess.run", return_value=mock.Mock(stdout="")):
            diag = wol.diagnose_wol(_fresh=True)
        self.assertIn("adapters", diag)
        self.assertIn("hints", diag)
        self.assertIsInstance(diag["adapters"], list)
        self.assertIn("os", diag)

    def test_diagnose_enriches_wireless_and_wired(self) -> None:
        getmac_csv = (
            '"连接名","网络适配器","物理地址"\n'
            '"Ethernet","Realtek PCIe GbE Family Controller","50-5A-65-04-4C-99"\n'
            '"Wi-Fi","MediaTek Wi-Fi 6 MT7921 Wireless LAN Card","AA-BB-CC-DD-EE-FF"\n'
            '"VMware Network Adapter VMnet1","VMware Virtual Ethernet Adapter for VMnet1","00-50-56-C0-00-01"\n'
        )
        fake = mock.Mock()
        fake.stdout = getmac_csv
        with mock.patch("wol.subprocess.run", return_value=fake):
            diag = wol.diagnose_wol(_fresh=True)
        # VMware 虚拟网卡应被过滤，只留真实有线 + 无线
        self.assertEqual(len(diag["adapters"]), 2)
        wired = [a for a in diag["adapters"] if not a["is_wireless"]]
        wireless = [a for a in diag["adapters"] if a["is_wireless"]]
        self.assertEqual(len(wired), 1)
        self.assertEqual(len(wireless), 1)
        self.assertEqual(wired[0]["mac"], "50-5A-65-04-4C-99")
        self.assertTrue(diag["wired_wol_ready"])
        self.assertTrue(diag["wifi_wo_wlan"])

    def test_diagnose_cache_reuses_result(self) -> None:
        getmac_csv = (
            '"连接名","网络适配器","物理地址"\n'
            '"Ethernet","Realtek PCIe GbE Family Controller","50-5A-65-04-4C-99"\n'
        )
        fake = mock.Mock()
        fake.stdout = getmac_csv
        with mock.patch("wol.subprocess.run", return_value=fake) as run_mock:
            first = wol.diagnose_wol(_fresh=True)
            second = wol.diagnose_wol()  # 应命中缓存，不再调 getmac
        self.assertEqual(first, second)
        self.assertEqual(run_mock.call_count, 1)

    def test_pick_default_target_prefers_wired(self) -> None:
        with mock.patch("wol.diagnose_wol", return_value={
            "adapters": [
                {"is_wireless": False, "mac": "50:5A:65:04:4C:99"},
                {"is_wireless": True, "mac": "AA:BB:CC:DD:EE:FF"},
            ],
        }):
            self.assertEqual(wol.pick_default_target_mac(), "50:5A:65:04:4C:99")


if __name__ == "__main__":
    unittest.main()
