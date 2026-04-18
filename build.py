import urllib.request, csv, json, io, datetime
from collections import defaultdict

SHEET = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSUbJANVTl4IScrjTiEjdUt_4oa_fsq_4J8jyt2TNnWaEuv76FYM9QE1I5EOq57aOnBxjcTW2lnZf0e/pub?gid=1476030811&single=true&output=csv"

CAT_NORM = {
    "New system- educational video V2 Sawal Jawab (App / Technical)": "New System Video - App/Technical",
    "New system- educational video V2 Sawal Jawab (NetBox)":          "New System Video - NetBox",
    "New system- educational video V2 Sawal Jawab (Netbox)":          "New System Video - NetBox",
    "New system - educational video (App / Technical)":               "New System Video - App/Technical",
    "New system - educational video (NetBox)":                        "New System Video - NetBox",
    "New system- educational video V2 Sawal Jawab (Other)":           "New System Video - Other",
    "New system- educational video V2 Sawal Jawab (Payout)":          "New System Video - Payout",
    "PNM Releted": "PNM Related", "Lead Releted": "Lead Related",
    "Lead flow": "Lead Flow",     "PAYGt": "PayG Basic Understanding",
    "ISP recharge Proof": "ISP Recharge Proof",
    "Want to Remove Lead": "Lead Related",
    "300 Security": "Rs300 Security Deposit",
    "Breach Fundamental Rule": "Fundamental Breach",
    "Recovery Rs50": "Recovery - Rs50 Pickup",
    "50 Rupees on Recovery": "Recovery - Rs50 Pickup",
    "New Project - 5 April Comms": "New Project Comms",
    "New Project- PayG Mumbai": "PayG Mumbai - New Project",
}
def nc(c): return CAT_NORM.get(c.strip(), c.strip())
def pd(d):
    p = d.split("/"); return (int(p[2]), int(p[0]), int(p[1]))

print("Fetching Google Sheet...")
req = urllib.request.Request(SHEET, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=30) as r:
    text = r.read().decode("utf-8-sig")

rows = []
reader = csv.reader(io.StringIO(text))
next(reader)
for row in reader:
    if len(row) >= 5 and row[0].strip():
        rows.append({
            "date":     row[0].strip(),
            "category": nc(row[1].strip()),
            "verbatim": row[3].strip(),
            "caller":   row[4].strip(),
            "partner":  (row[5].strip() if len(row) > 5 else ""),
            "priority": ((row[6].strip() if len(row) > 6 else "NA") or "NA"),
        })
print(f"Fetched {len(rows)} rows")

DAY = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
MON = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

by_date = defaultdict(lambda: defaultdict(list))
for r in rows:
    by_date[r["date"]][r["category"]].append(r)

dates = sorted(by_date.keys(), key=pd)
data  = {}
for date in dates:
    p  = date.split("/")
    dt = datetime.date(int(p[2]), int(p[0]), int(p[1]))
    total = sum(len(v) for v in by_date[date].values())
    cats  = sorted(by_date[date].items(), key=lambda x: -len(x[1]))
    data[date] = {
        "total":   total,
        "display": f"{DAY[dt.weekday()]}, {p[1]} {MON[int(p[0])]}",
        "day": DAY[dt.weekday()], "dd": p[1], "mm": MON[int(p[0])],
        "categories": [{
            "name": cat, "count": len(recs),
            "pct":  round(len(recs) / total * 100, 1),
            "records": [{"v": r["verbatim"], "p": r["priority"], "partner": r["partner"]} for r in recs]
        } for cat, recs in cats]
    }

allcats = sorted(set(r["category"] for r in rows),
                 key=lambda c: -sum(1 for r in rows if r["category"] == c))
matrix  = {cat: [sum(1 for r in rows if r["category"] == cat and r["date"] == d)
                 for d in dates] for cat in allcats}
dlabels = []
for d in dates:
    p  = d.split("/")
    dt = datetime.date(int(p[2]), int(p[0]), int(p[1]))
    dlabels.append(f"{DAY[dt.weekday()]} {p[1]}/{p[0]}")

mdata = {
    "categories":  allcats,
    "dates":       dates,
    "date_labels": dlabels,
    "date_totals": [data[d]["total"] for d in dates],
    "matrix":      matrix,
}

now = datetime.datetime.utcnow().strftime("%d %b %Y %H:%M UTC")

with open("template.html", encoding="utf-8") as f:
    tmpl = f.read()

html = tmpl.replace("__DATA__",    json.dumps(data,  ensure_ascii=False))
html = html.replace("__MATRIX__",  json.dumps(mdata, ensure_ascii=False))
html = html.replace("__UPDATED__", now)
html = html.replace("__TOTAL__",   str(len(rows)))
html = html.replace("__DAYS__",    str(len(dates)))

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"Done! index.html built — {len(rows)} rows, {len(dates)} dates, updated {now}")
