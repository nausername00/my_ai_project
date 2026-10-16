"""T4 系统层：TLS 挂载默认关/启用、状态端点 tls/auto_start 如实上报。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ssl

import app
import api


def _make_pem_pair(tmp: Path) -> tuple[str, str]:
    """用 cryptography 生成临时 PEM（自签证书 + 私钥），供 TLS 加载测试。"""
    import datetime
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "T4 Test Cert")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp / "cert.pem"
    key_path = tmp / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return str(cert_path), str(key_path)


class WrapTlsTest(unittest.TestCase):
    """wrap_tls：默认关（零配置即明文）、文件缺失报错、配置后真实 TLS 包装。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.server = app.create_server("127.0.0.1", 0)

    def tearDown(self) -> None:
        self.server.server_close()
        self.tmp.cleanup()

    @patch.dict(os.environ, {}, clear=False)
    def test_default_off_returns_plain_server(self) -> None:
        os.environ.pop("MOLING_TLS_CERT", None)
        os.environ.pop("MOLING_TLS_KEY", None)
        result = app.wrap_tls(self.server)
        self.assertIs(result, self.server)
        self.assertFalse(isinstance(self.server.socket, ssl.SSLSocket))

    @patch.dict(os.environ, {}, clear=False)
    def test_missing_files_raise(self) -> None:
        os.environ["MOLING_TLS_CERT"] = str(Path(self.tmp.name) / "nope.pem")
        os.environ["MOLING_TLS_KEY"] = str(Path(self.tmp.name) / "nope_key.pem")
        with self.assertRaises(FileNotFoundError):
            app.wrap_tls(self.server)

    @patch.dict(os.environ, {}, clear=False)
    def test_configured_wraps_socket(self) -> None:
        cert, key = _make_pem_pair(Path(self.tmp.name))
        os.environ["MOLING_TLS_CERT"] = cert
        os.environ["MOLING_TLS_KEY"] = key
        result = app.wrap_tls(self.server)
        self.assertIs(result, self.server)
        self.assertIsInstance(self.server.socket, ssl.SSLSocket)


class SelfHostStatusTest(unittest.TestCase):
    """_self_host_status：tls 字段随环境配置如实变化；auto_start 读注册表（mock）。"""

    def tearDown(self) -> None:
        os.environ.pop("MOLING_TLS_CERT", None)
        os.environ.pop("MOLING_TLS_KEY", None)

    def test_tls_false_by_default(self) -> None:
        self.assertFalse(api._self_host_status()["tls"])

    def test_tls_true_when_configured(self) -> None:
        os.environ["MOLING_TLS_CERT"] = "C:/certs/cert.pem"
        os.environ["MOLING_TLS_KEY"] = "C:/certs/key.pem"
        self.assertTrue(api._self_host_status()["tls"])

    @patch("api._auto_start_installed", return_value=True)
    def test_auto_start_reported_true(self, _mock: object) -> None:
        self.assertTrue(api._self_host_status()["auto_start"])

    @patch("api._auto_start_installed", return_value=False)
    def test_auto_start_reported_false(self, _mock: object) -> None:
        self.assertFalse(api._self_host_status()["auto_start"])


if __name__ == "__main__":
    unittest.main()
