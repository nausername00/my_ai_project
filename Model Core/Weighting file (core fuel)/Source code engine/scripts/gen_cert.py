"""gen_cert.py —— 用 cryptography 生成 OpenSSL 兼容的自签名证书（方案 A）。

输出（%LOCALAPPDATA%\\MOLING\\certs\\）：
  moling_cert.pem  公钥证书（PEM，BEGIN CERTIFICATE）
  moling_key.pem   私钥（PEM，BEGIN RSA PRIVATE KEY，无加密）
  moling_cert.cer  证书 DER（供 Windows Import-Certificate 导入信任库）

幂等：证书与私钥已存在且能被 ssl 加载时直接复用（不重生成、不换指纹）。
首次生成打印一行 `GENERATED <fingerprint>`；复用时打印 `REUSED <fingerprint>`。

依赖：cryptography（pip install cryptography）；仅生成期使用，服务运行不依赖。
"""

import base64
import datetime
import ipaddress
import os
import ssl
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERTS_DIR = Path(os.environ.get("LOCALAPPDATA", ".")) / "MOLING" / "certs"
CERT_PATH = CERTS_DIR / "moling_cert.pem"
KEY_PATH = CERTS_DIR / "moling_key.pem"
CER_PATH = CERTS_DIR / "moling_cert.cer"
SUBJECT = "MOLING Local Service"


def pems_usable() -> bool:
    """证书与私钥已存在且能被 ssl 加载视为可复用。"""
    if not (CERT_PATH.exists() and KEY_PATH.exists()):
        return False
    try:
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(
            str(CERT_PATH), str(KEY_PATH)
        )
        return True
    except Exception:
        return False


def fingerprint(der: bytes) -> str:
    import hashlib

    return hashlib.sha256(der).hexdigest().upper()


def main() -> int:
    CERTS_DIR.mkdir(parents=True, exist_ok=True)

    if pems_usable():
        der = CER_PATH.read_bytes() if CER_PATH.exists() else CERT_PATH.read_bytes()
        try:
            cert = x509.load_pem_x509_certificate(CERT_PATH.read_bytes())
            fp = fingerprint(cert.public_bytes(serialization.Encoding.DER))
        except Exception:
            fp = "?"
        print(f"REUSED {fp}")
        return 0

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, SUBJECT),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MOLING"),
        ]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1825))  # 5 年
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    x509.IPAddress(ipaddress.ip_address("::1")),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )
        .sign(key, hashes.SHA256())
    )

    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    KEY_PATH.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    CER_PATH.write_bytes(cert.public_bytes(serialization.Encoding.DER))

    fp = fingerprint(cert.public_bytes(serialization.Encoding.DER))
    print(f"GENERATED {fp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
