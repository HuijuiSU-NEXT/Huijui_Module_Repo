import requests, json, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if TOKEN: HEADERS["Authorization"] = f"token {TOKEN}"

session = requests.Session()
retries = Retry(total=3, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

BLACKLIST = [
    "format", "rm -rf", "dd if=", "cheat", "hack", "trojan", "steal",
    "外挂", "作弊", "透视", "自瞄", "aimbot", "wallhack", "executor", "injector",
    "gameguardian", "lucky_patcher"
]

QUERIES = [
    "topic:kernelsu", "topic:magisk-module", "topic:magisk", "topic:apatch",
    "kernelsu in:name,description", "magisk in:name,description",
    "topic:zygisk", "topic:zygisk-module", "zygisk in:name,description",
    "topic:lsposed", "topic:lsposed-module", "topic:xposed",
    "topic:metamodule", "metamodule in:name,description,readme",
    "hybrid-mount in:name,description", "meta-hybrid_mount in:name,description"
]

TRUSTED_DEVS = [
    "topjohnwu", "tiann", "5ec1cff", "sorubedo", "wangtong10086",
    "hhcdxii-ship-it", "Dr-TSNG", "PerformanC", "LSPosed"
]

CATEGORY_KEYWORDS = {
    "performance": ["性能", "调度", "cpu", "内存", "优化", "performance", "tuning", "省电", "内核", "gpu"],
    "gaming": ["游戏", "触控", "gaming", "fps", "高刷"],
    "media": ["音效", "相机", "屏幕", "音频", "camera", "audio", "display", "拍照", "vulkan"],
    "network": ["网络", "dns", "广告", "hosts", "proxy", "去广告", "拦截"],
    "system": ["系统", "内核", "框架", "framework", "system", "integrity", "playintegrity", "修复"],
    "privacy": ["隐私", "隐藏", "反检测", "hide", "privacy", "spoof", "伪装", "zygisk", "lsposed", "hybrid"],
    "theme": ["美化", "字体", "主题", "ui", "theme", "font", "bootanimation", "开机动画", "图标"],
    "utility": ["工具", "终端", "文件", "utility", "tool", "terminal", "清理", "管理"]
}

def guess_category(desc):
    desc_lower = desc.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                return cat
    return "utility"

def get_trust_level(author, stars):
    if author.lower() in [a.lower() for a in TRUSTED_DEVS]:
        return "TRUSTED_DEV"
    elif stars >= 50:
        return "COMMUNITY"
    return "UNVERIFIED"

def load_old_modules():
    if os.path.exists("modules.json"):
        try:
            with open("modules.json", "r", encoding="utf-8") as f:
                return {m["id"]: m for m in json.load(f)}
        except Exception:
            pass
    return {}

def search_repos():
    all_repos = {}
    print("Start scanning...", flush=True)
    for q in QUERIES:
        print(f"Searching: {q} ...", flush=True)
        for page in range(1, 4):
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
                time.sleep(2)
            except Exception:
                pass
    return all_repos

def get_module_data(repo_name, repo_info, old_modules):
    old_data = old_modules.get(repo_name.replace("/", "_"))
    pushed_at = repo_info.get("pushed_at", "")
    stars = repo_info.get("stargazers_count", 0)

    # 🚀 核心修复：缓存自愈机制
    if old_data and old_data.get("updatedAt") == pushed_at:
        old_data["stars"] = stars
        # 如果旧缓存缺少新字段，现场补全，防止 KeyError
        if "module_type" not in old_data:
            old_data["module_type"] = "standard"
        if "category" not in old_data:
            old_data["category"] = guess_category(old_data.get("description", ""))
        if "trust_level" not in old_data:
            old_data["trust_level"] = get_trust_level(old_data.get("author", ""), stars)
        if "has_webui" not in old_data:
            old_data["has_webui"] = "webui" in old_data.get("description", "").lower()
        return old_data

    try:
        resp = session.get(f"https://api.github.com/repos/{repo_name}/releases", headers=HEADERS, timeout=10)
        if resp.status_code != 200: return None
        releases_data = resp.json()
        if not releases_data: return None

        valid_releases = []
        for rel in releases_data[:5]:
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
        desc_text = (releases_data[0].get("body") or "No description").replace("\n", " ")
        module_type = "standard"

        for branch in ["main", "master"]:
            prop_url = f"https://raw.githubusercontent.com/{repo_name}/{branch}/module.prop"
            try:
                prop_resp = session.get(prop_url, timeout=5)
                if prop_resp.status_code == 200:
                    for line in prop_resp.text.splitlines():
                        if line.startswith("version="):
                            real_ver = line.split("=", 1)[1].strip()
                        if line.startswith("metamodule=") and line.split("=", 1)[1].strip() in ["1", "true"]:
                            if "hybrid" in repo_name.lower() or "hybrid" in desc_text.lower():
                                module_type = "hybrid_mount"
                            else:
                                module_type = "metamodule"
            except Exception: pass

            xposed_url = f"https://raw.githubusercontent.com/{repo_name}/{branch}/META-INF/xposed/module.prop"
            try:
                xposed_resp = session.get(xposed_url, timeout=5)
                if xposed_resp.status_code == 200:
                    module_type = "lsposed"
                    break
            except Exception: pass

            if module_type == "standard":
                if "zygisk" in repo_name.lower() or "zygisk" in desc_text.lower():
                    module_type = "zygisk"

        if len(desc_text) > 200:
            desc_text = desc_text[:200] + "..."

        module_data = {
            "id": repo_name.replace("/", "_"),
            "name": repo_name.split("/")[1],
            "author": repo_name.split("/")[0],
            "version": real_ver,
            "description": desc_text,
            "module_type": module_type,
            "category": guess_category(desc_text),
            "trust_level": get_trust_level(repo_name.split("/")[0], stars),
            "has_webui": "webui" in desc_text.lower(),
            "downloadCount": latest["downloadCount"],
            "updatedAt": pushed_at,
            "stars": stars,
            "releases": [latest]
        }
        return module_data
    except Exception:
        return None

def main():
    old_modules = load_old_modules()
    all_repos = search_repos()
    print(f"\nFound {len(all_repos)} candidates. Starting deep scan...", flush=True)
    modules = []

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(get_module_data, repo, info, old_modules): repo for repo, info in all_repos.items()}
        for i, f in enumerate(as_completed(futures)):
            rep = f.result()
            if rep:
                modules.append(rep)
                if i % 50 == 0:
                    # 🚀 修复：用 get() 兜底，防止日志打崩
                    print(f"[{i}/{len(all_repos)}] OK: {rep.get('name', 'unknown')} [{rep.get('module_type', 'standard')}]", flush=True)

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
