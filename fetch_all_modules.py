import requests, json, os, time, re
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if TOKEN: HEADERS["Authorization"] = f"token {TOKEN}"

# 🚨 终极防格机黑名单
BLACKLIST = [
    "format", "rm -rf", "dd if=", "cheat", "hack", "trojan", "steal", "keybox",
    "格机", "删库", "病毒", "wipe", "erase", "loop", "brick"
]

# 🚀 生成上千种搜索组合，突破 GitHub 1000 条限制
def generate_queries():
    base_queries = [
        "kernelsu", "magisk", "lsposed", "zygisk", "susfs", "magisk-module", 
        "xposed", "root", "kernel", "recovery", "gki", "hide", "spoof"
    ]
    modifiers = ["", " in:name", " in:description", " in:readme", " topic:magisk", " topic:kernelsu", " language:kotlin", " language:shell", " stars:>10", " stars:>50"]
    queries = set()
    for b in base_queries:
        for m in modifiers:
            queries.add(f"{b}{m}")
    return list(queries)

QUERIES = generate_queries()

def clean_text(text):
    if not text: return "暂无描述"
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'[#\*`>]', '', text)
    return text[:100].strip() + "..."

def get_tags(repo_name, desc):
    text = (repo_name + " " + (desc or "")).lower()
    tags = []
    if any(k in text for k in ["kernel", "gki", "susfs"]): tags.append("内核底层")
    if any(k in text for k in ["hide", "shamiko", "tricky", "spoof", "env"]): tags.append("环境隐藏")
    if any(k in text for k in ["zygisk", "lsposed", "xposed", "hook"]): tags.append("XP注入")
    if any(k in text for k in ["audio", "sound", "font", "emoji", "theme", "ui", "美化"]): tags.append("视觉美化")
    if any(k in text for k in ["battery", "thermal", "charge", "perf", "sched", "调度"]): tags.append("性能调度")
    if not tags: tags.append("实用工具")
    return tags

def search_repos():
    all_repos = {}
    print(f"🚀 启动核弹级扫描，共 {len(QUERIES)} 个组合词，预计耗时 10-20 分钟...", flush=True)
    for i, q in enumerate(QUERIES):
        print(f"[{i+1}/{len(QUERIES)}] 搜索: {q} ...", flush=True)
        # 每个词只抓 1 页（100个），但词多，总量惊人
        url = f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page=100"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for r in items:
                    if r.get("fork", False): continue
                    # 严格的黑名单匹配
                    if not any(w in r["full_name"].lower() or w in (r.get("description") or "").lower() for w in BLACKLIST):
                        all_repos[r["full_name"]] = r
            elif resp.status_code == 403:
                print("⚠️ 触发限流，休息 10 秒...", flush=True)
                time.sleep(10)
        except Exception as e: pass
        time.sleep(1.5) # 防封延时
    return all_repos

def get_module_data(repo, repo_info):
    try:
        resp = requests.get(f"https://api.github.com/repos/{repo}/releases", headers=HEADERS, timeout=10)
        if resp.status_code != 200: return None
        releases_data = resp.json()
        if not releases_data: return None

        valid_releases = []
        for rel in releases_data[:3]:
            zip_asset = next((a for a in rel.get("assets", []) if a["name"].endswith(".zip")), None)
            if zip_asset:
                size_mb = zip_asset["size"] / (1024 * 1024)
                if 0.001 <= size_mb <= 200:
                    valid_releases.append({
                        "name": rel.get("tag_name", "Unknown"),
                        "publishedAt": rel.get("published_at", ""),
                        "zipUrl": zip_asset["browser_download_url"],
                        "size": zip_asset["size"],
                        "downloadCount": zip_asset.get("download_count", 0)
                    })
        if not valid_releases: return None
        
        latest = valid_releases[0]
        raw_desc = releases_data[0].get("body") or repo_info.get("description") or ""
        
        # 尝试拿真实版本号
        real_ver = latest["name"]
        for branch in ["main", "master"]:
            prop_url = f"https://raw.githubusercontent.com/{repo}/{branch}/module.prop"
            try:
                prop_resp = requests.get(prop_url, timeout=5)
                if prop_resp.status_code == 200:
                    for line in prop_resp.text.splitlines():
                        if line.startswith("version="):
                            real_ver = line.split("=", 1)[1].strip()
                    break
            except Exception: pass

        return {
            "id": repo.replace("/", "_"),
            "name": repo.split("/")[1],
            "author": repo.split("/")[0],
            "version": real_ver,
            "description": clean_text(raw_desc),
            "tags": get_tags(repo, raw_desc),
            "downloadCount": latest["downloadCount"],
            "stars": repo_info.get("stargazers_count", 0),
            "updatedAt": latest["publishedAt"],
            "releases": valid_releases
        }
    except Exception: return None

def main():
    all_repos = search_repos()
    print(f"\n📦 全网共锁定 {len(all_repos)} 个候选仓库！启动 20 线程深度质检...", flush=True)
    modules = []
    
    # 🚀 使用 20 线程并发
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(get_module_data, repo, info): repo for repo, info in all_repos.items()}
        for i, f in enumerate(as_completed(futures)):
            rep = f.result()
            if rep:
                modules.append(rep)
                if len(modules) % 100 == 0:
                    print(f"✅ 已成功收录 {len(modules)} 个有效模块...", flush=True)
    
    # 去重
    unique_mods = {}
    for m in modules:
        if m["id"] not in unique_mods or m["downloadCount"] > unique_mods[m["id"]]["downloadCount"]:
            unique_mods[m["id"]] = m
            
    final_list = list(unique_mods.values())
    final_list.sort(key=lambda x: x["updatedAt"], reverse=True)
    
    with open("modules.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)
    print(f"\n🎉 终极核弹扫描完毕！去重后共收录 {len(final_list)} 个安全模块！", flush=True)

if __name__ == "__main__":
    main()
