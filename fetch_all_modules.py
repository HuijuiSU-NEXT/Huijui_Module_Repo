import requests
import json
import os
import time

TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if TOKEN:
    HEADERS["Authorization"] = f"token {TOKEN}"

QUERIES = ["topic:kernelsu", "topic:magisk-module", "topic:android-root"]

# 🚨 黑名单：包含这些关键词的仓库/描述/脚本，直接踢掉
BLACKLIST_KEYWORDS = [
    "格机", "删库", "病毒", "木马", "cheat", "hack", "trojan", "steal", 
    "format", "rm -rf", "dd if=/dev/zero", "过风控", "过检测"
]

def is_safe(repo_name, description):
    text = (repo_name + " " + (description or "")).lower()
    # 1. 名字和描述黑名单检测
    for word in BLACKLIST_KEYWORDS:
        if word in text:
            print(f"⛔ 拦截高危模块 (描述含黑名单关键词 {word}): {repo_name}")
            return False
    return True

def get_latest_release(repo):
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/releases/latest", headers=HEADERS
    )
    if resp.status_code != 200:
        return None
    data = resp.json()

    zip_asset = next(
        (a for a in data.get("assets", []) if a["name"].endswith(".zip")), None
    )
    if not zip_asset:
        return None

    # 2. 体积安检：超过 20MB 的模块极度可疑，直接拒绝；小于 10KB 的是空包，也拒绝
    size_mb = zip_asset["size"] / (1024 * 1024)
    if size_mb > 20 or size_mb < 0.01:
        print(f"⚠️ 体积异常，拦截: {repo} ({size_mb:.2f} MB)")
        return None

    # 尝试从仓库根目录读取 module.prop
    module_prop_url = f"https://raw.githubusercontent.com/{repo}/main/module.prop"
    prop_resp = requests.get(module_prop_url, headers=HEADERS)
    update_json = ""
    if prop_resp.status_code == 200:
        for line in prop_resp.text.splitlines():
            if line.startswith("updateJson="):
                update_json = line.split("=", 1)[1].strip()

    return {
        "id": repo.replace("/", "_"),
        "name": repo.split("/")[1],
        "version": data.get("tag_name", "Unknown"),
        "versionCode": 1,
        "author": repo.split("/")[0],
        "description": (data.get("body") or "")[:80].replace("\n", " "),
        "zipUrl": zip_asset["browser_download_url"],
        "updateJson": update_json,
        "size": zip_asset["size"],
        "updatedAt": data.get("published_at", ""),
    }

def main():
    all_repos = {}
    for q in QUERIES:
        resp = requests.get(
            f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page=50",
            headers=HEADERS,
        )
        if resp.status_code == 200:
            for r in resp.json().get("items", []):
                # 🚨 3. 仓库信誉门槛：Star 数少于 2 的新号小号，直接不要（防批量注册的恶意号）
                if r.get("stargazers_count", 0) < 2:
                    continue
                
                # 4. 描述安检
                if not is_safe(r["full_name"], r.get("description")):
                    continue

                all_repos[r["full_name"]] = r
        time.sleep(1)

    modules = []
    for repo in all_repos:
        mod = get_latest_release(repo)
        if mod:
            modules.append(mod)
            print(f"✅ 收录通过: {repo} - {mod['version']}")
        time.sleep(0.3)

    modules.sort(key=lambda x: x["updatedAt"], reverse=True)
    with open("modules.json", "w", encoding="utf-8") as f:
        json.dump(modules, f, indent=2, ensure_ascii=False)
    print(f"🎉 安检完毕，共收录 {len(modules)} 个安全模块")

if __name__ == "__main__":
    main()
