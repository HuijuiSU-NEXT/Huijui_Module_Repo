import requests
import json
import os
import time

TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {
    "Accept": "application/vnd.github.v3+json",
}
if TOKEN:
    HEADERS["Authorization"] = f"token {TOKEN}"
else:
    print("⚠️ 警告: 没有检测到 GITHUB_TOKEN，API 限流只有 60次/小时，搜不到几个就会报错！")

QUERIES = [
    "topic:kernelsu",
    "topic:magisk-module",
    "topic:android-root"
]

def search_repositories(query):
    # 按最近更新排序
    url = f"https://api.github.com/search/repositories?q={query}&sort=updated&order=desc&per_page=50"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return resp.json().get("items", [])
    print(f"❌ 搜索失败: {query}, 状态码: {resp.status_code}")
    return []

def get_latest_release(repo_full_name):
    url = f"https://api.github.com/repos/{repo_full_name}/releases/latest"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return None
    
    data = resp.json()
    download_url = ""
    size = 0
    for asset in data.get("assets", []):
        if asset["name"].endswith(".zip"):
            download_url = asset["browser_download_url"]
            size = asset["size"]
            break
            
    if not download_url:
        return None

    # 风控过滤黑名单，防呆
    blacklist_keywords = ["cheat", "hack", "steal", "trojan"]
    repo_name_lower = repo_full_name.lower()
    if any(k in repo_name_lower for k in blacklist_keywords):
        print(f"⛔ 跳过疑似危险模块: {repo_full_name}")
        return None

    return {
        "id": repo_full_name.replace("/", "_"),
        "name": repo_full_name.split("/")[1],
        "version": data.get("tag_name", "Unknown"),
        "author": repo_full_name.split("/")[0],
        "description": (data.get("body") or "暂无说明")[:80].replace('\n', ' ') + "...",
        "repo": f"https://github.com/{repo_full_name}",
        "zipUrl": download_url,
        "size": size,
        "updated_at": data.get("published_at", "")
    }

def main():
    all_repos = {}
    
    print("🚀 开始全网搜刮 KernelSU 模块...")
    for q in QUERIES:
        print(f"🔍 正在搜索: {q}")
        repos = search_repositories(q)
        for r in repos:
            all_repos[r["full_name"]] = r
        time.sleep(1)
    
    print(f"📦 搜到 {len(all_repos)} 个相关仓库，开始校验 Release...")
    
    valid_modules = []
    for repo_name in all_repos.keys():
        mod = get_latest_release(repo_name)
        if mod:
            valid_modules.append(mod)
            print(f"✅ 收录: {repo_name} - {mod['version']}")
        time.sleep(0.5)

    valid_modules.sort(key=lambda x: x["updated_at"], reverse=True)

    with open("modules.json", "w", encoding="utf-8") as f:
        json.dump(valid_modules, f, indent=4, ensure_ascii=False)
    print(f"🎉 成功生成 modules.json，共包含 {len(valid_modules)} 个有效模块！")

if __name__ == "__main__":
    main()
