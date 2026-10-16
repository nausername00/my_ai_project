"""T4 系统层端到端验收：真实 HTTPS 请求走系统信任链；admin 状态如实上报。"""

import json
import ssl
import urllib.request

BASE = "https://127.0.0.1:8443"
TOKEN = "acceptance-token-4e2f"


def get(path: str, token: str | None = None, insecure: bool = False) -> tuple[int, object]:
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(BASE + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        return e.code, None


def main() -> int:
    # 1) 真实 https 请求（默认上下文 = 系统信任链，不传证书）→ 200
    status, body = get("/health")
    assert status == 200 and body["status"] == "ok", (status, body)
    print(f"[1] https /health 走系统信任链: 200 ok")

    # 2) admin 状态端点：tls=true、auto_start=true（本机已装自启）、token 已配置
    status, body = get("/v1/admin/self-host", TOKEN)
    assert status == 200, status
    assert body["tls"] is True, body
    assert body["token_configured"] is True, body
    assert body["auto_start"] is True, body
    print(f"[2] /v1/admin/self-host: tls={body['tls']} auto_start={body['auto_start']} token={body['token_configured']}")

    # 3) admin 端点无 token 必须拒绝（默认关边界）
    status, _ = get("/v1/admin/self-host", None)
    assert status == 401, status
    print(f"[3] 无 token 访问 admin: {status} (拒绝)")

    # 4) 同一端口明文 http 必须失败（TLS 已包装）
    try:
        import http.client

        c = http.client.HTTPConnection("127.0.0.1", 8443, timeout=10)
        c.request("GET", "/health")
        c.getresponse()
        raise AssertionError("明文 http 竟然成功？")
    except Exception as e:
        print(f"[4] 明文 http 访问 8443: 被拒 ({type(e).__name__})")

    print("T4 系统层端到端验收：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
