"""Diagnostic: how fresh is the raw.githubusercontent copy of dashboard.json?"""
import json, random, time, urllib.request
B = "https://raw.githubusercontent.com/ostromaj/paper-trail-2/data/dashboard.json"
def get(u, h=None):
    with urllib.request.urlopen(urllib.request.Request(u, headers=h or {}), timeout=15) as r:
        return r.headers, json.loads(r.read())
for label, url in [("plain", B), ("query", B + f"?t={random.randint(1,10**9)}"), ("query2", B + f"?cb={time.time()}")]:
    h, s = get(url)
    print(label, "age_of_data_s", int(time.time() - s["last_run"]), "| Age", h.get("Age"), "| X-Cache", h.get("X-Cache"), "| CC", h.get("Cache-Control"), "| ACAO", h.get("Access-Control-Allow-Origin"))
h, s = get("https://api.github.com/repos/ostromaj/paper-trail-2/contents/dashboard.json?ref=data", {"Accept": "application/vnd.github.raw+json", "User-Agent": "probe"})
print("api age_of_data_s", int(time.time() - s["last_run"]), "| remaining", h.get("X-RateLimit-Remaining"), "limit", h.get("X-RateLimit-Limit"))
h, s = get("https://api.github.com/repos/ostromaj/paper-trail-2/branches/data", {"User-Agent": "probe"})
sha = s["commit"]["sha"]
h, s = get(f"https://raw.githubusercontent.com/ostromaj/paper-trail-2/{sha}/dashboard.json")
print("raw-by-sha age_of_data_s", int(time.time() - s["last_run"]), "| ACAO", h.get("Access-Control-Allow-Origin"))
