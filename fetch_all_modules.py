import requests, json, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if TOKEN: HEADERS["Authorization"] = f"token {TOKEN}"

# 加入自动重试，应对偶尔的 429/503 限流
session = requests.Session()
retries = Retry(total=3, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

BLACKLIST = ["format", "rm -rf", "dd if=", "cheat", "hack", "trojan", "steal"]

# 扩充了搜索关键词和 topic，尽量捞全
QUERIES = [
    "topic:kernelsu", "topic:magisk-module", "topic:magisk",
    "topic:lsposed", "topic:zygisk", "topic:susfs", "topic:apatch",
    "kernelsu in:name,description", "magisk in:name,description",
    "magisk in:readme", "kernelsu in:readme"
]

def load_old_modules():
    # 读取上一次生成的 modules.json 作为缓存
    if os.path.exists("modules.json"):
        try:
            with open("modules.json", "r", encoding="utf-8") as f:
                return {m["id"]: m for m in json.load(f)}
        except Exception: pass
    return {}

def search_repos():
    all_repos = {}
    print("Start scanning...", flush=True)
    for q in QUERIES:
        print(f"Searching: {q} ...", flush=True)
        # 扩大到 10 页 (最多1000个)，充分榨干搜索额度
        for page in range(1, 11):
            url = f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page=100&page={page}"
            try:
                resp = session.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    if not items: break
                    for r in items:
                        if r.get("fork", False): continue
                        if not any(w in r["full_name"].lower() for w in BLACKLIST):
                            all_repos[r["full_name"]] = r
                time.sleep(2) # 控制搜索频率
            except Exception: pass
    return all_repos

def get_module_data(repo_name, repo_info, old_modules):
    # 【核心优化】增量缓存：如果仓库上次提交时间没变，直接复用旧数据，不再请求 API！
    old_data = old_modules.get(repo_name.replace("/", "_"))
    pushed_at = repo_info.get("pushed_at", "")
    
    if old_data and old_data.get("updatedAt") == pushed_at:
        old_data["stars"] = repo_info.get("stargazers_count", 0) # 更新星星数
        return old_data
        
    try:
        resp = session.get(f"https://api.github.com/repos/{repo_name}/releases", headers=HEADERS, timeout=10)
        if resp.status_code != 200: return None
        releases_data = resp.json()
        if not releases_data: return None

        valid_releases = []
        for rel in releases_data[:5]:
            # 放开了 .apk 和 .tgz 等格式限制
            asset = next((a for a in rel.get("assets", []) if a["name"].endswith((".zip", ".apk", ".tgz"))), None)
            if asset:
                size_mb = asset["size"] / (1024 * 1024)
                if 0.001 <= size_mb <= 200:
                    valid_releases.append({
                        "name": rel.get("tag_name", "Unknown"),
                        "publishedAt": rel.get("published_at", ""),
                        "zipUrl": asset["browser_download_url"],
                        "size": asset["size"],
                        "downloadCount": asset.get("download_count", 0)
                    })
        if not valid_releases: return None
        valid_releases.sort(key=lambda x: x["publishedAt"], reverse=True)
        latest = valid_releases[0]

        real_ver = latest["name"]
        for branch in ["main", "master"]:
            prop_url = f"https://raw.githubusercontent.com/{repo_name}/{branch}/module.prop"
            try:
                prop_resp = session.get(prop_url, timeout=5)
                if prop_resp.status_code == 200:
                    for line in prop_resp.text.splitlines():
                        if line.startswith("version="):
                            real_ver = line.split("=", 1)[1].strip()
                    break
            except Exception: pass

        return {
            "id": repo_name.replace("/", "_"),
            "name": repo_name.split("/")[1],
            "author": repo_name.split("/")[0],
            "version": real_ver,
            "description": (releases_data[0].get("body") or "No description")[:120].replace("\n", " "),
            "downloadCount": latest["downloadCount"],
            "updatedAt": pushed_at, # 用 pushed_at 替代发布时间，用于下次比对
            "stars": repo_info.get("stargazers_count", 0),
            "releases": valid_releases
        }
    except Exception: return None

def main():
    old_modules = load_old_modules()
    all_repos = search_repos()
    print(f"\nFound {len(all_repos)} candidates. Starting deep scan...", flush=True)
    modules = []
    
    # 【核心优化】并发降到 5，防止被 API 拉黑限流
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(get_module_data, repo, info, old_modules): repo for repo, info in all_repos.items()}
        for i, f in enumerate(as_completed(futures)):
            rep = f.result()
            if rep:
                modules.append(rep)
                # 每隔50个打印一次，减少日志输出卡顿
                if i % 50 == 0:
                    print(f"[{i}/{len(all_repos)}] OK: {rep['name']}", flush=True)

    unique_modules = {}
    for mod in modules:
        if mod["id"] not in unique_modules or mod["downloadCount"] > unique_modules[mod["id"]]["downloadCount"]:
            unique_modules[mod["id"]] = mod

    final_list = list(unique_modules.values())
    final_list.sort(key=lambda x: x.get("updatedAt", ""), reverse=True)

    with open("modules.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)
    print(f"\nDone! Total unique modules: {len(final_list)}", flush=True)

if __name__ == "__main__":
    main()
