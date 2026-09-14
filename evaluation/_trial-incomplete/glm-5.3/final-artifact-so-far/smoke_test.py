"""启动 uvicorn 并请求 /health 与完整流程，验证本地可运行。输出结果到 smoke_result.txt。"""
import json
import subprocess
import sys
import time
import urllib.request

PORT = 8137
BASE = f"http://127.0.0.1:{PORT}"
PY = sys.executable

proc = subprocess.Popen(
    [PY, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
    cwd="D:/Workspace/trial-workspaces/glm-5.3",
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
lines = []
try:
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=1) as r:
                lines.append(f"GET /health -> {r.status} {r.read().decode()}")
                break
        except Exception:
            time.sleep(0.5)
    else:
        raise RuntimeError("server did not start")

    def call(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            BASE + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    s, order = call("POST", "/orders", {
        "user_id": "smoke-user",
        "items": [{"sku_id": "s1", "name": "耳机", "price": 199.0, "quantity": 2}],
    })
    lines.append(f"POST /orders -> {s} total={order.get('total_amount')}")
    s, r = call("POST", f"/orders/{order['id']}/pay")
    lines.append(f"pay -> {s} {r.get('status')}")
    s, a = call("POST", f"/orders/{order['id']}/after-sales", {"reason": "smoke 退款"})
    lines.append(f"after-sale -> {s} {a.get('status')}")
    s, r = call("POST", f"/after-sales/{a['id']}/approve")
    lines.append(f"approve -> {s} {r.get('status')}")
    s, r = call("POST", f"/after-sales/{a['id']}/refund")
    lines.append(f"refund -> {s} {r.get('status')}")
    s, r = call("GET", f"/orders/{order['id']}")
    lines.append(f"order status -> {s} {r.get('status')}")
    lines.append("SMOKE OK" if r.get("status") == "REFUNDED" else "SMOKE FAIL")
finally:
    proc.terminate()
    proc.wait(timeout=10)

with open("D:/Workspace/trial-workspaces/glm-5.3/smoke_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
