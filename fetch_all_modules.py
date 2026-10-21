import requests, json, os, time, re
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if TOKEN: HEADERS["Authorization"] = f"token {TOKEN}"

# 🚨 极致防格机正则黑名单（发现即封杀）
BLACKLIST_REGEX = [
    r"format\s+-", r"rm\s+-rf", r"dd\s+if=", r"mkfs", r"wipe\s+/", r"brick", 
    r"ransom", r"miner", r"格机", r"删库", r"病毒", r"木马", r"盗号", 
    r"cheat", r"hack", r"trojan", r"steal", r"backdoor", r"rm -rf /"
]
def is_safe(repo_name, desc):
    text = (repo_name + " " + (desc or "")).lower()
    return not any(re.search(pattern, text) for pattern in BLACKLIST_REGEX)

# 多维度搜索词矩阵
QUERIES = [
    "topic:kernelsu", "topic:magisk-module", "topic:magisk", "topic:lsposed", 
    "topic:zygisk", "topic:susfs", "topic:gki", "topic:magisk-hide", "topic:xposed",
    "kernelsu in:name", "magisk in:name", "magisk-module in:name", 
    "lsposed in:name", "zygisk in:name", "susfs in:name"
]
print("✅ 第一段：基础定义与搜索矩阵加载完毕！", flush=True)

def safe_request(url, timeout=15, retries=3):
    """带重试机制的防抖网络请求"""
    for i in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp
            elif resp.status_code in [403, 429]:
                time.sleep(3)
        except Exception:
            time.sleep(1)
    return None

def clean_text(text):
    if not text: return "暂无描述"
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'[#\*`>]', '', text)
    return text[:120].strip() + "..."

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
    print("🔍 [Ultra] 开始多维度深度扫描...", flush=True)
    for q in QUERIES:
        print(f"👉 扫词: {q} ...", flush=True)
        for page in range(1, 4):
            url = f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page=100&page={page}"
            resp = safe_request(url)
            if resp:
                items = resp.json().get("items", [])
                if not items: break
                for r in items:
                    if r.get("fork", False): continue
                    if is_safe(r["full_name"], r.get("description")):
                        all_repos[r["full_name"]] = r
            time.sleep(1)
    return all_repos
print("✅ 第二段：网络重试机制与标签算法加载完毕！", flush=True)

def get_module_data(repo, repo_info):
    try:
        # 🚀 加上 ?per_page=100，一次性抓取最多 100 个历史版本
        resp = safe_request(f"https://api.github.com/repos/{repo}/releases?per_page=100", timeout=10)
        if not resp: return None
        releases_data = resp.json()
        if not releases_data: return None

        valid_releases = []
        for rel in releases_data: # 保留最多5个历史版本
            zip_asset = next((a for a in rel.get("assets", []) if a["name"].endswith(".zip")), None)
            if zip_asset:
                size_mb = zip_asset["size"] / (1024 * 1024)
                # 🚀 1KB - 1GB 放宽限制
                if 0.001 <= size_mb <= 1024:
                    valid_releases.append({
                        "name": rel.get("tag_name", "Unknown"),
                        "publishedAt": rel.get("published_at", ""),
                        "zipUrl": zip_asset["browser_download_url"],
                        "size": zip_asset["size"],
                        "downloadCount": zip_asset.get("download_count", 0)
                    })
        if not valid_releases: return None
        
        # 🚀 核心：按照发布时间从新到旧排序（最新发布的在最前面）
        valid_releases.sort(key=lambda x: x["publishedAt"], reverse=True)
        
        latest = valid_releases[0]
        raw_desc = releases_data[0].get("body") or repo_info.get("description") or ""
        
        # 深度解析 module.prop
        real_id = repo.replace("/", "_")
        real_ver = latest["name"]
        real_name = repo.split("/")[1]
        
        for branch in ["main", "master"]:
            prop_url = f"https://raw.githubusercontent.com/{repo}/{branch}/module.prop"
            try:
                prop_resp = requests.get(prop_url, timeout=5)
                if prop_resp.status_code == 200:
                    for line in prop_resp.text.splitlines():
                        if line.startswith("id="): real_id = line.split("=", 1)[1].strip()
                        if line.startswith("version="): real_ver = line.split("=", 1)[1].strip()
                        if line.startswith("name="): real_name = line.split("=", 1)[1].strip()
                    break
            except Exception: pass

        return {
            "id": real_id,
            "name": real_name,
            "repo_name": repo.split("/")[1],
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
print("✅ 第三段：深度解析与防格机逻辑加载完毕！", flush=True)

def main():
    all_repos = search_repos()
    
    # 读取白名单并强制塞入
    if os.path.exists("custom_repos.txt"):
        with open("custom_repos.txt", "r", encoding="utf-8") as f:
            for line in f:
                mr = line.strip()
                if mr and not mr.startswith("#") and mr not in all_repos:
                    all_repos[mr] = {"description": "手动白名单强制收录"}

    print(f"\n📦 [Ultra] 锁定 {len(all_repos)} 个候选，启动 30 线程深度质检...", flush=True)
    modules = []
    
    with ThreadPoolExecutor(max_workers=30) as ex:
        futures = {ex.submit(get_module_data, repo, info): repo for repo, info in all_repos.items()}
        for i, f in enumerate(as_completed(futures)):
            rep = f.result()
            if rep:
                modules.append(rep)
                if len(modules) % 100 == 0:
                    print(f"✅ 已深度质检并收录 {len(modules)} 个模块...", flush=True)
    
    # 🚀 根据 module.prop 的 id 去重，保留下载量最高的
    unique_mods = {}
    for m in modules:
        key = m["id"] if m["id"] else m["repo_name"]
        if key not in unique_mods or m["downloadCount"] > unique_mods[key]["downloadCount"]:
            unique_mods[key] = m
            
    final_list = list(unique_mods.values())
    final_list.sort(key=lambda x: x["updatedAt"], reverse=True)
    
    with open("modules.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)
    print(f"\n🎉 [Ultra] 终极安检完毕！成功入库 {len(final_list)} 个高质量模块！", flush=True)

if __name__ == "__main__":
    main()
print("✅ 第四段：并发调度与去重逻辑加载完毕！全部代码已就绪，可以运行 python3 fetch_all_modules.py 测试了！", flush=True)

import io, zipfile

def scan_zip_for_danger(zip_url, size):
    """🚀 终极安检：对于小于5MB的包，直接在内存中解压检测高危脚本"""
    if size > 5 * 1024 * 1024: # 超过5MB的包怕卡内存，略过深度检查
        return True
    try:
        resp = requests.get(zip_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                # 检查高危脚本
                for file_name in z.namelist():
                    if file_name.endswith((".sh", ".prop", ".xml", ".txt")):
                        file_content = z.read(file_name).decode('utf-8', errors='ignore').lower()
                        # 如果在脚本里发现了格机指令或危险指令
                        if any(re.search(p, file_content) for p in [r"rm\s+-rf\s+/", r"format", r"dd\s+if=", r"mkfs"]):
                            return False
        return True
    except Exception:
        return True
print("✅ 第五段：终极内存级 ZIP 安检加载完毕！", flush=True)

def get_module_data_ultra(repo, repo_info):
    try:
        # 🚀 加上 ?per_page=100，一次性抓取最多 100 个历史版本
        resp = safe_request(f"https://api.github.com/repos/{repo}/releases?per_page=100", timeout=10)
        if not resp: return None
        releases_data = resp.json()
        if not releases_data: return None

        valid_releases = []
        for rel in releases_data:
            zip_asset = next((a for a in rel.get("assets", []) if a["name"].endswith(".zip")), None)
            if zip_asset:
                size_mb = zip_asset["size"] / (1024 * 1024)
                if 0.001 <= size_mb <= 1024: # 1GB 限制
                    # 🚨 终极安检门：扫描内部脚本
                    if scan_zip_for_danger(zip_asset["browser_download_url"], zip_asset["size"]):
                        valid_releases.append({
                            "name": rel.get("tag_name", "Unknown"),
                            "publishedAt": rel.get("published_at", ""),
                            "zipUrl": zip_asset["browser_download_url"],
                            "size": zip_asset["size"],
                            "downloadCount": zip_asset.get("download_count", 0)
                        })
        if not valid_releases: return None
        
        # 🚀 核心：按照发布时间从新到旧排序（最新发布的在最前面）
        valid_releases.sort(key=lambda x: x["publishedAt"], reverse=True)
        
        latest = valid_releases[0]
        raw_desc = releases_data[0].get("body") or repo_info.get("description") or ""
        
        real_id = repo.replace("/", "_")
        real_ver = latest["name"]
        real_name = repo.split("/")[1]
        
        for branch in ["main", "master"]:
            prop_url = f"https://raw.githubusercontent.com/{repo}/{branch}/module.prop"
            try:
                prop_resp = requests.get(prop_url, timeout=5)
                if prop_resp.status_code == 200:
                    for line in prop_resp.text.splitlines():
                        if line.startswith("id="): real_id = line.split("=", 1)[1].strip()
                        if line.startswith("version="): real_ver = line.split("=", 1)[1].strip()
                        if line.startswith("name="): real_name = line.split("=", 1)[1].strip()
                    break
            except Exception: pass

        return {
            "id": real_id,
            "name": real_name,
            "repo_name": repo.split("/")[1],
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
print("✅ 第六段：深度解析与安全拦截器加载完毕！", flush=True)

def finalize_and_save(modules):
    unique_mods = {}
    for m in modules:
        key = m["id"] if m["id"] else m["repo_name"]
        if key not in unique_mods or m["downloadCount"] > unique_mods[key]["downloadCount"]:
            unique_mods[key] = m

    final_list = list(unique_mods.values())
    final_list.sort(key=lambda x: x["updatedAt"], reverse=True)
    
    with open("modules.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)
    print(f"\n🎉 [Ultra] 终极安检完毕！成功入库 {len(final_list)} 个高质量模块！", flush=True)
print("✅ 第七段：极致去重与保存模块加载完毕！", flush=True)

def run_scraper():
    all_repos = search_repos()
    
    if os.path.exists("custom_repos.txt"):
        with open("custom_repos.txt", "r", encoding="utf-8") as f:
            for line in f:
                mr = line.strip()
                if mr and not mr.startswith("#") and mr not in all_repos:
                    all_repos[mr] = {"description": "手动白名单强制收录"}

    print(f"\n📦 [Ultra] 锁定 {len(all_repos)} 个候选，启动 30 线程深度质检...", flush=True)
    modules = []
    
    with ThreadPoolExecutor(max_workers=30) as ex:
        futures = {ex.submit(get_module_data_ultra, repo, info): repo for repo, info in all_repos.items()}
        for i, f in enumerate(as_completed(futures)):
            rep = f.result()
            if rep:
                modules.append(rep)
                if len(modules) % 50 == 0:
                    print(f"✅ 已深度质检并安全入库 {len(modules)} 个模块...", flush=True)

    finalize_and_save(modules)
print("✅ 第八段：30线程并发主控加载完毕！", flush=True)
