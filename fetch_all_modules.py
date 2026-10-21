import requests, json, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if TOKEN: HEADERS["Authorization"] = f"token {TOKEN}"

BLACKLIST = ["format", "rm -rf", "dd if=", "cheat", "hack", "trojan", "steal"]
QUERIES = [
    "topic:kernelsu", "topic:magisk-module", "topic:magisk", 
    "topic:lsposed", "topic:zygisk", "topic:susfs",
    "kernelsu in:name,description", "magisk in:name,description"
]

def search_repos():
    all_repos = {}
    print("Start scanning...", flush=True)
    for q in QUERIES:
        print(f"Searching: {q} ...", flush=True)
        for page in range(1, 6):
            url = f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page=100&page={page}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    if not items: break
                    for r in items:
                        if r.get("fork", False): continue
                        if not any(w in r["full_name"].lower() for w in BLACKLIST):
                            all_repos[r["full_name"]] = r
            except Exception: pass
            time.sleep(2)
    return all_repos

def get_module_data(repo):
    try:
        resp = requests.get(f"https://api.github.com/repos/{repo}/releases", headers=HEADERS, timeout=10)
        if resp.status_code != 200: return None
        releases_data = resp.json()
        if not releases_data: return None

        valid_releases = []
        for rel in releases_data[:5]:
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
        valid_releases.sort(key=lambda x: x["publishedAt"], reverse=True)
        latest = valid_releases[0]

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
            "description": (releases_data[0].get("body") or "No description")[:120].replace("\n", " "),
            "downloadCount": latest["downloadCount"],
            "updatedAt": latest["publishedAt"],
            "releases": valid_releases
        }
    except Exception: return None

def main():
    all_repos = search_repos()
    print(f"\nFound {len(all_repos)} candidates. Starting deep scan...", flush=True)
    modules = []
    with ThreadPoolExecutor(max_workers=15) as ex:
        futures = {ex.submit(get_module_data, repo): repo for repo in all_repos}
        for i, f in enumerate(as_completed(futures)):
            rep = f.result()
            if rep:
                rep["stars"] = all_repos[futures[f]].get("stargazers_count", 0)
                modules.append(rep)
                print(f"[{i+1}/{len(all_repos)}] OK: {rep['name']}", flush=True)
            else:
                print(f"[{i+1}/{len(all_repos)}] SKIP: {futures[f]}", flush=True)
    
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
