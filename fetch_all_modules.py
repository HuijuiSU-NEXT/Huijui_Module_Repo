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

# 扩充黑名单：过滤代码、外挂、恶意注入等
BLACKLIST = [
    "format", "rm -rf", "dd if=", "cheat", "hack", "trojan", "steal",
    "外挂", "作弊", "透视", "自瞄", "aimbot", "wallhack", "executor", "injector",
    "gameguardian", "lucky_patcher"
]

# 扩充搜索关键词，精准覆盖各类底层模块
QUERIES = [
    # 基础模块
    "topic:kernelsu", "topic:magisk-module", "topic:magisk", "topic:apatch",
    "kernelsu in:name,description", "magisk in:name,description",
    # Zygisk
    "topic:zygisk", "topic:zygisk-module", "zygisk in:name,description",
    # LSPosed / Xposed
    "topic:lsposed", "topic:lsposed-module", "topic:xposed",
    # MetaModule & Hybrid Mount
    "topic:metamodule", "metamodule in:name,description,readme",
    "hybrid-mount in:name,description", "meta-hybrid_mount in:name,description"
]

# 信任的开发者白名单
TRUSTED_DEVS = [
    "topjohnwu", "tiann", "5ec1cff", "sorubedo", "wangtong10086",
    "hhcdxii-ship-it", "Dr-TSNG", "PerformanC", "LSPosed"
]

# 分类关键词映射
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
        for page in range(1, 4):  # 每个关键词最多取前 3 页 (300个)，平衡效率
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

    # 【增量缓存】如果仓库上次提交时间没变，直接复用旧数据，更新星标数即可
    if old_data and old_data.get("updatedAt") == pushed_at:
        old_data["stars"] = stars
        return old_data

    try:
        resp = session.get(f"https://api.github.com/repos/{repo_name}/releases", headers=HEADERS, timeout=10)
        if resp.status_code != 200: return None
        releases_data = resp.json()
        if not releases_data: return None

        valid_releases = []
        for rel in releases_data[:5]:
            # 放宽支持 .zip, .apk, .tgz 格式
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

        # 🚀 核心探测逻辑
        for branch in ["main", "master"]:
            # 1. 检查 module.prop 判断版本和 MetaModule
            prop_url = f"https://raw.githubusercontent.com/{repo_name}/{branch}/module.prop"
            try:
                prop_resp = session.get(prop_url, timeout=5)
                if prop_resp.status_code == 200:
                    for line in prop_resp.text.splitlines():
                        if line.startswith("version="):
                            real_ver = line.split("=", 1)[1].strip()
                        if line.startswith("metamodule=") and line.split("=", 1)[1].strip() in ["1", "true"]:
                            # 是 MetaModule，再检查是否为 Hybrid Mount
                            if "hybrid" in repo_name.lower() or "hybrid" in desc_text.lower():
                                module_type = "hybrid_mount"
                            else:
                                module_type = "metamodule"
            except Exception: pass

            # 2. 检查 LSPosed 特征文件
            xposed_url = f"https://raw.githubusercontent.com/{repo_name}/{branch}/META-INF/xposed/module.prop"
            try:
                xposed_resp = session.get(xposed_url, timeout=5)
                if xposed_resp.status_code == 200:
                    module_type = "lsposed"
                    break # 确认是 LSPosed 就停止后续探测
            except Exception: pass

            # 3. Zygisk 兜底判断（如果当前还不是特殊模块，且名字或描述带 zygisk）
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
            "module_type": module_type, # 🚀 模块类型：standard / zygisk / lsposed / metamodule / hybrid_mount
            "category": guess_category(desc_text),
            "trust_level": get_trust_level(repo_name.split("/")[0], stars),
            "has_webui": "webui" in desc_text.lower(),
            "downloadCount": latest["downloadCount"],
            "updatedAt": pushed_at,
            "stars": stars,
            "releases": [latest] # 只保留最新版本，减小体积
        }
        return module_data
    except Exception:
        return None

def main():
    old_modules = load_old_modules()
    all_repos = search_repos()
    print(f"\nFound {len(all_repos)} candidates. Starting deep scan...", flush=True)
    modules = []

    # 并发降为 5，防止被 GitHub API 拉黑
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(get_module_data, repo, info, old_modules): repo for repo, info in all_repos.items()}
        for i, f in enumerate(as_completed(futures)):
            rep = f.result()
            if rep:
                modules.append(rep)
                if i % 50 == 0:
                    print(f"[{i}/{len(all_repos)}] OK: {rep['name']} [{rep['module_type']}]", flush=True)

    # 按 ID 去重，保留下载量最高的
    unique_modules = {}
    for mod in modules:
        if mod["id"] not in unique_modules or mod["downloadCount"] > unique_modules[mod["id"]]["downloadCount"]:
            unique_modules[mod["id"]] = mod

    final_list = list(unique_modules.values())
    # 按照更新时间倒序排列
    final_list.sort(key=lambda x: x.get("updatedAt", ""), reverse=True)

    with open("modules.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)
    print(f"\nDone! Total unique modules: {len(final_list)}", flush=True)

if __name__ == "__main__":
    main()
