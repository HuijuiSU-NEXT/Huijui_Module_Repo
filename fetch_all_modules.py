import requests
import json
import os
import time

TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if TOKEN:
    HEADERS["Authorization"] = f"token {TOKEN}"

# 🚀 扩充关键词，一网打尽所有玩机生态
QUERIES = [
    "topic:kernelsu", 
    "topic:magisk-module", 
    "topic:magisk", 
    "topic:lsposed", 
    "topic:zygisk"
]

# 🚨 致命黑名单：防止格机、木马、病毒
BLACKLIST_KEYWORDS = [
    "格机", "删库", "病毒", "木马", "cheat", "hack", "trojan", "steal", 
    "format", "rm -rf", "dd if=/dev/zero", "dd if="
]

def is_safe(repo_name, description):
    text = (repo_name + " " + (description or "")).lower()
    for word in BLACKLIST_KEYWORDS:
        if word in text:
            print(f"⛔ 拦截高危模块 (包含 {word}): {repo_name}", flush=True)
            return False
    return True

def get_latest_release(repo):
    try:
        # 强制 10 秒超时，防止云端卡死
        resp = requests.get(f"https://api.github.com/repos/{repo}/releases/latest", headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        # 寻找 .zip 附件
        zip_asset = next((a for a in data.get("assets", []) if a["name"].endswith(".zip")), None)
        if not zip_asset:
            return None
        
        # 🚨 体积限制放宽至 200MB，放行内核包
        size_mb = zip_asset["size"] / (1024 * 1024)
        if size_mb > 200 or size_mb < 0.001:
            print(f"⚠️ 体积异常拦截: {repo} ({size_mb:.2f} MB)", flush=True)
            return None

        return {
            "id": repo.replace("/", "_"),
            "name": repo.split("/")[1],
            "version": data.get("tag_name", "Unknown"),
            "versionCode": 1,
            "author": repo.split("/")[0],
            "description": (data.get("body") or "暂无描述")[:100].replace("\n", " "),
            "zipUrl": zip_asset["browser_download_url"],
            "size": zip_asset["size"],
            "stars": data.get("stargazers_count", 0),
            "updatedAt": data.get("published_at", ""),
        }
    except Exception:
        return None

def main():
    print("🚀 开始全网搜刮模块...", flush=True)
    all_repos = {}
    
    # 遍历所有关键词
    for q in QUERIES:
        print(f"🔍 正在搜索: {q} ...", flush=True)
        # 抓取前 3 页 (每页 100 个，共 300 个)
        for page in [1, 2, 3]:
            try:
                url = f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page=100&page={page}"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    if not items:
                        break
                    print(f"   -> 第 {page} 页找到 {len(items)} 个仓库", flush=True)
                    for r in items:
                        if not is_safe(r["full_name"], r.get("description")): 
                            continue
                        all_repos[r["full_name"]] = r
                elif resp.status_code == 403:
                    print(f"   ❌ 触发 API 限流，稍作休息...", flush=True)
                    time.sleep(10)
                else:
                    print(f"   ❌ 搜索失败，状态码: {resp.status_code}", flush=True)
            except Exception as e:
                print(f"   ❌ 网络异常: {e}", flush=True)
            time.sleep(2) # 每页之间休息2秒防封

    print(f"\n📦 初步扫描完毕，共 {len(all_repos)} 个相关仓库进入深度安检...", flush=True)

    modules = []
    # 逐个获取 Release 信息
    for i, repo in enumerate(all_repos):
        print(f"[{i+1}/{len(all_repos)}] 检查: {repo} ... ", end="", flush=True)
        mod = get_latest_release(repo)
        if mod:
            modules.append(mod)
            print("✅ 收录", flush=True)
        else:
            print("❌ 跳过 (无 Release 或体积异常)", flush=True)
        time.sleep(0.3) # 防止请求过快被拦截

    # 按更新时间排序（最新的在最前）
    modules.sort(key=lambda x: x.get("updatedAt", ""), reverse=True)
    
    # 写入 JSON
    with open("modules.json", "w", encoding="utf-8") as f:
        json.dump(modules, f, indent=2, ensure_ascii=False)
    print(f"\n🎉 终极安检完毕！共收录 {len(modules)} 个安全模块！", flush=True)

if __name__ == "__main__":
    main()
