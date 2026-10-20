import requests
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if TOKEN:
    HEADERS["Authorization"] = f"token {TOKEN}"

# 🚨 黑名单
BLACKLIST_KEYWORDS = [
    "格机", "删库", "病毒", "木马", "cheat", "hack", "trojan", "steal", 
    "format", "rm -rf", "dd if=", "ransom", "miner"
]

def load_manual_list(filename):
    if not os.path.exists(filename): return []
    with open(filename, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

def is_safe(repo_name, description):
    text = (repo_name + " " + (description or "")).lower()
    return not any(word in text for word in BLACKLIST_KEYWORDS)

# 全网雷达词库
QUERIES = [
    "topic:kernelsu", 
    "topic:magisk-module", 
    "topic:lsposed", 
    "kernelsu in:name,description",
    "magisk in:name,description"
]

def safe_requests_get(url, timeout=10, retries=3):
    """带重试机制的请求，防止网络抖动或限流"""
    for i in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp
            elif resp.status_code == 403:
                print(f"   [限流] 休息 5 秒后重试: {url}", flush=True)
                time.sleep(5)
            else:
                return None
        except Exception:
            time.sleep(2)
    return None

def search_repos():
    all_repos = {}
    manual_repos = load_manual_list("custom_repos.txt")
    print(f"🔒 已加载手动白名单：{len(manual_repos)} 个仓库", flush=True)
    for repo in manual_repos:
        all_repos[repo] = {"full_name": repo, "description": "手动添加"}

    for q in QUERIES:
        print(f"🔍 雷达扫描: {q} ...", flush=True)
        for page in [1, 2, 3]:
            url = f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page=100&page={page}"
            resp = safe_requests_get(url, timeout=15)
            if resp:
                items = resp.json().get("items", [])
                if not items: break
                for r in items:
                    # 过滤小号、Fork出来的重复项目
                    if r.get("stargazers_count", 0) < 2 or r.get("fork", False): 
                        continue
                    if not is_safe(r["full_name"], r.get("description")): 
                        continue
                    all_repos[r["full_name"]] = r
            time.sleep(1)
    return all_repos

def get_module_info(repo_full_name):
    try:
        # 1. 查最新 Release
        resp = safe_requests_get(f"https://api.github.com/repos/{repo_full_name}/releases/latest")
        if not resp: return None
        
        data = resp.json()
        zip_asset = next((a for a in data.get("assets", []) if a["name"].endswith(".zip")), None)
        if not zip_asset: return None

        size_mb = zip_asset["size"] / (1024 * 1024)
        if size_mb > 200 or size_mb < 0.001: return None

        # 2. 提取真实 module.prop (兼容 main 和 master)
        real_id = repo_full_name.replace("/", "_")
        real_ver = data.get("tag_name", "Unknown")
        real_ver_code = 1
        
        for branch in ["main", "master"]:
            prop_url = f"https://raw.githubusercontent.com/{repo_full_name}/{branch}/module.prop"
            prop_resp = requests.get(prop_url, headers=HEADERS, timeout=5)
            if prop_resp.status_code == 200:
                for line in prop_resp.text.splitlines():
                    if line.startswith("id="): real_id = line.split("=", 1)[1].strip()
                    if line.startswith("version="): real_ver = line.split("=", 1)[1].strip()
                    if line.startswith("versionCode="): 
                        try: real_ver_code = int(line.split("=", 1)[1].strip())
                        except: pass
                break # 找到了就跳出分支循环

        return {
            "id": real_id,
            "name": repo_full_name.split("/")[1],
            "version": real_ver,
            "versionCode": real_ver_code,
            "author": repo_full_name.split("/")[0],
            "description": (data.get("body") or "暂无描述")[:100].replace("\n", " "),
            "zipUrl": zip_asset["browser_download_url"],
            "size": zip_asset["size"],
            "stars": data.get("stargazers_count", 0),
            "downloadCount": zip_asset.get("download_count", 0), # 🚀 新增下载量！
            "updatedAt": data.get("published_at", ""),
        }
    except Exception:
        return None

def main():
    all_repos = search_repos()
    print(f"\n📦 搜出 {len(all_repos)} 个候选，启动 15 线程安检...", flush=True)

    modules = []
    # 使用15线程，速度与防封的完美平衡
    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_repo = {executor.submit(get_module_info, repo): repo for repo in all_repos}
        
        for i, future in enumerate(as_completed(future_to_repo)):
            repo = future_to_repo[future]
            try:
                mod = future.result()
                if mod:
                    modules.append(mod)
                    print(f"[{i+1}/{len(all_repos)}] ✅ 收录: {repo}", flush=True)
                else:
                    print(f"[{i+1}/{len(all_repos)}] ❌ 跳过", flush=True)
            except Exception:
                pass

    # 🚀 终极去重逻辑：如果有相同 id，只保留下载量最高的那个
    unique_modules = {}
    for mod in modules:
        mod_id = mod["id"]
        if mod_id not in unique_modules or mod["downloadCount"] > unique_modules[mod_id]["downloadCount"]:
            unique_modules[mod_id] = mod

    final_modules = list(unique_modules.values())
    
    # 按更新时间倒序（最新发布的排前面）
    final_modules.sort(key=lambda x: x.get("updatedAt", ""), reverse=True)
    
    with open("modules.json", "w", encoding="utf-8") as f:
        json.dump(final_modules, f, indent=2, ensure_ascii=False)
    
    print(f"\n🎉 超级进化完毕！去重后共收录 {len(final_modules)} 个极品模块！", flush=True)

if __name__ == "__main__":
    main()
