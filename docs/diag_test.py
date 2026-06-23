"""
Sayit API 连通性诊断脚本（最小可运行版本）
用法: python docs/diag_test.py
从 config.json 读取配置，不硬编码任何 key
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"[错误] config.json 不存在: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def mask_key(k):
    if not k or len(k) < 10:
        return "(空)" if not k else f"(长度={len(k)}, 需要检查格式)"
    return k[:6] + "…" + k[-4:]

def test_http_endpoint(name, url, headers, body=None, timeout=15):
    """基础 HTTP 连通性测试"""
    import urllib.request
    import urllib.error
    try:
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body else "GET")
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw = resp.read().decode("utf-8", errors="replace")
        return True, resp.status, raw[:500]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return False, e.code, body[:500]
    except Exception as e:
        return False, None, str(e)[:500]

def main():
    cfg = load_config()
    print("=" * 60)
    print("Sayit API 连通性诊断")
    print("=" * 60)

    # ── 1. 检查本地服务 ──
    print("\n[1] 本地服务状态")
    print(f"  config.json: {CONFIG_PATH}")
    print(f"  asr_engine:  {cfg.get('asr_engine', '(未配置)')}")
    asr_order = cfg.get("asr_fallback", {}).get("order", [])
    print(f"  asr_fallback.order: {asr_order}")

    # ── 2. DashScope (阿里云) ──
    print("\n[2] DashScope (阿里云灵积)")
    aliyun = cfg.get("aliyun", {})
    aliyun_key = aliyun.get("api_key", "")
    print(f"  api_key: {mask_key(aliyun_key)}")
    if aliyun_key and "…" not in aliyun_key:
        headers = {"Authorization": f"Bearer {aliyun_key}", "Content-Type": "application/json"}
        body = {
            "model": aliyun.get("asr_model", "qwen3-asr-flash"),
            "input": {"messages": [{"role": "user", "content": "测试"}]},
            "parameters": {"max_tokens": 1}
        }
        ok, code, resp = test_http_endpoint(
            "DashScope", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers, body)
        print(f"  结果: {'OK' if ok else 'FAIL'} HTTP {code}")
        print(f"  响应: {resp}")
    else:
        print("  [跳过] 未配置有效 API Key")

    # ── 3. Volcengine (火山方舟) ASR ──
    print("\n[3] Volcengine (火山方舟) ASR")
    volc = cfg.get("volcengine", {}).get("asr", {})
    volc_key = volc.get("api_key", "") or volc.get("access_token", "")
    print(f"  api_key: {mask_key(volc_key)}")
    print(f"  app_id: {volc.get('app_id', '(空)')}")
    print(f"  endpoint: {volc.get('endpoint', '(空)')}")
    if volc_key and "…" not in volc_key:
        # 尝试 v2 HTTP 端点
        import urllib.request
        try:
            # 简单的连通性测试 — 用 HEAD 请求
            req = urllib.request.Request("https://openspeech.bytedance.com/api/v1/asr", method="HEAD")
            resp = urllib.request.urlopen(req, timeout=10)
            print(f"  端点可达: HTTP {resp.status}")
        except urllib.error.HTTPError as e:
            print(f"  端点可达: HTTP {e.code} (预期需要 auth)")
        except Exception as e:
            print(f"  端点不可达: {e}")
    else:
        print("  [跳过] 未配置有效 API Key")

    # ── 4. Volcengine AI (豆包) ──
    print("\n[4] Volcengine AI (豆包大模型)")
    volc_ai = cfg.get("volcengine", {}).get("ai", {})
    volc_ai_key = volc_ai.get("api_key", "")
    print(f"  api_key: {mask_key(volc_ai_key)}")
    print(f"  endpoint: {volc_ai.get('endpoint', '(空)')}")
    if volc_ai_key and "…" not in volc_ai_key:
        ep = volc_ai.get("endpoint", "https://ark.cn-beijing.volces.com/api/v3")
        if "/chat/completions" not in ep:
            ep = ep.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {volc_ai_key}", "Content-Type": "application/json"}
        body = {"model": volc_ai.get("correction_model", "doubao-seed-2-0-lite-260428"),
                "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
        ok, code, resp = test_http_endpoint("豆包AI", ep, headers, body)
        print(f"  结果: {'OK' if ok else 'FAIL'} HTTP {code}")
        print(f"  响应: {resp}")
    else:
        print("  [跳过] 未配置有效 API Key")

    # ── 5. DeepSeek ──
    print("\n[5] DeepSeek")
    ds_key = cfg.get("deepseek", {}).get("api_key", "")
    # 也检查 ai_providers 中的 deepseek
    if not ds_key:
        for p in cfg.get("ai_providers", []):
            if p.get("id") == "deepseek":
                ds_key = p.get("api_key", "")
                break
    print(f"  api_key: {mask_key(ds_key)}")
    if ds_key and "…" not in ds_key:
        headers = {"Authorization": f"Bearer {ds_key}", "Content-Type": "application/json"}
        body = {"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
        ok, code, resp = test_http_endpoint("DeepSeek", "https://api.deepseek.com/v1/chat/completions", headers, body)
        print(f"  结果: {'OK' if ok else 'FAIL'} HTTP {code}")
        print(f"  响应: {resp}")
    else:
        print("  [跳过] 未配置有效 API Key")

    # ── 6. ai_providers 列表 ──
    print("\n[6] ai_providers 配置")
    providers = cfg.get("ai_providers", [])
    if not providers:
        print("  [警告] ai_providers 为空 — AI 润色功能不可用")
    else:
        for p in providers:
            pid = p.get("id", "?")
            enabled = p.get("enabled", True)
            key = p.get("api_key", "")
            print(f"  [{pid}] enabled={enabled} key={mask_key(key)} model={p.get('model', '?')}")

    # ── 7. 依赖检查 ──
    print("\n[7] Python 依赖检查")
    deps = {
        "fastapi": "FastAPI 后端框架",
        "uvicorn": "ASGI 服务器",
        "dashscope": "阿里云 DashScope SDK",
        "httpx": "HTTP 客户端",
        "pyaudio": "音频采集",
        "pyperclip": "剪贴板操作",
        "pynput": "键盘监听",
        "numpy": "数值计算",
        "comtypes": "COM/UIA 接口",
        "websocket": "WebSocket 客户端 (v3 ASR)",
        "onnxruntime": "ONNX 本地 ASR 推理",
    }
    for mod, desc in deps.items():
        try:
            __import__(mod.replace("-", "_"))
            print(f"  [OK] {mod} — {desc}")
        except ImportError:
            print(f"  [缺失] {mod} — {desc}")

    # ── 8. 本地 ONNX 模型 ──
    print("\n[8] ONNX 本地模型")
    onnx_dir = cfg.get("asr_fallback", {}).get("onnx_model_dir", "")
    if not onnx_dir:
        onnx_dir = os.path.join(PROJECT_ROOT, "models", "sensevoice")
    onnx_file = os.path.join(onnx_dir, "model.onnx")
    tokens_file = os.path.join(onnx_dir, "tokens.json")
    print(f"  目录: {onnx_dir}")
    print(f"  model.onnx: {'存在' if os.path.exists(onnx_file) else '缺失'}")
    print(f"  tokens.json: {'存在' if os.path.exists(tokens_file) else '缺失'}")
    # 检查 iic 目录格式
    iic_dir = os.path.join(PROJECT_ROOT, "models", "sensevoice", "iic", "SenseVoiceSmall")
    iic_model = os.path.join(iic_dir, "model.pt")
    print(f"  SenseVoiceSmall model.pt: {'存在' if os.path.exists(iic_model) else '缺失（需从 ModelScope 下载）'}")

    # ── 9. 总结 ──
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)
    issues = []
    if not aliyun_key or "…" in aliyun_key:
        issues.append("DashScope API Key 未配置 → ASR 主引擎不可用")
    if not volc_key or "…" in volc_key:
        issues.append("Volcengine ASR Key 未配置 → 火山 ASR 不可用")
    if not providers:
        issues.append("ai_providers 列表为空 → AI 润色不可用")
    if issues:
        for i in issues:
            print(f"  [严重] {i}")
    else:
        # 检查依赖
        missing_deps = []
        for mod, desc in deps.items():
            try:
                __import__(mod.replace("-", "_"))
            except ImportError:
                missing_deps.append(mod)
        if missing_deps:
            print(f"  [警告] 缺失依赖: {', '.join(missing_deps)}")
        else:
            print("  [OK] 所有服务配置完整且依赖就绪")
    print()

if __name__ == "__main__":
    main()
