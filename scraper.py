import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

DATA_FILE = "data.json"


def fetch_html(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_members(html):
    """Liest Name + Punkte aus der Mitglieder-Rangliste.
    Best-effort-Parser: sucht die Überschrift "Mitglieder-Rangliste",
    steigt von dort so weit im DOM nach oben, bis ein Container mit
    mehreren Links auf /users/... gefunden wird, und liest pro Link
    den Namen sowie die naechstgelegene "X Pkt"-Zahl aus.
    """
    soup = BeautifulSoup(html, "html.parser")

    anchor_text = soup.find(string=re.compile(r"Mitglieder-Rangliste"))
    container = anchor_text.parent if anchor_text else soup

    node = container
    for _ in range(6):
        if node is None:
            break
        links = node.find_all("a", href=re.compile(r"/users/"))
        if len(links) >= 2:
            container = node
            break
        node = node.parent

    member_links = container.find_all("a", href=re.compile(r"/users/"))

    members = []
    seen_hrefs = set()
    for link in member_links:
        href = link.get("href")
        if not href or href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        name = link.get_text(strip=True)
        if not name:
            continue
        # Falls der Name noch ein angehaengtes "admin" enthaelt
        name = re.sub(r"\s+admin$", "", name).strip()

        points = None
        row = link
        for _ in range(5):
            row = row.parent
            if row is None:
                break
            text = row.get_text(" ", strip=True)
            matches = re.findall(r"(\d+)\s*Pkt", text)
            if matches:
                points = int(matches[-1])
                break

        if points is not None:
            members.append({"name": name, "points": points})

    return members


def slugify_id(name, existing_ids):
    base = re.sub(r"[^a-z0-9]+", "", name.lower()) or "spieler"
    candidate = base
    i = 2
    while candidate in existing_ids:
        candidate = f"{base}{i}"
        i += 1
    return candidate


def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    html = fetch_html(data["srfUrl"])
    members = parse_members(html)

    if not members:
        raise SystemExit(
            "Keine Mitglieder gefunden. Die Seite hat sich vermutlich geaendert, "
            "der Parser in parse_members() muss angepasst werden."
        )

    existing_by_name = {p["name"]: p["id"] for p in data["players"]}
    existing_ids = set(existing_by_name.values())

    points_by_id = {}
    for m in members:
        if m["name"] in existing_by_name:
            pid = existing_by_name[m["name"]]
        else:
            pid = slugify_id(m["name"], existing_ids)
            existing_ids.add(pid)
            data["players"].append({"id": pid, "name": m["name"]})
            existing_by_name[m["name"]] = pid
        points_by_id[pid] = m["points"]

    today = datetime.now(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%d")

    snapshots = data["snapshots"]
    existing_idx = next((i for i, s in enumerate(snapshots) if s["date"] == today), None)
    snapshot = {"date": today, "points": points_by_id}
    if existing_idx is not None:
        snapshots[existing_idx] = snapshot
    else:
        snapshots.append(snapshot)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Snapshot {today}: {points_by_id}")


if __name__ == "__main__":
    main()
