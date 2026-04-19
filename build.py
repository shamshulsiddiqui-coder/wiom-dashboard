import urllib.request, csv, json, io, datetime, time, os, re
from collections import defaultdict

SHEET = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSUbJANVTl4IScrjTiEjdUt_4oa_fsq_4J8jyt2TNnWaEuv76FYM9QE1I5EOq57aOnBxjcTW2lnZf0e/pub?gid=1476030811&single=true&output=csv"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

CAT_NORM = {
    "New system- educational video V2 Sawal Jawab (App / Technical)": "New System Video - App/Technical",
    "New system- educational video V2 Sawal Jawab (NetBox)":          "New System Video - NetBox",
    "New system- educational video V2 Sawal Jawab (Netbox)":          "New System Video - NetBox",
    "New system - educational video (App / Technical)":               "New System Video - App/Technical",
    "New system - educational video (NetBox)":                        "New System Video - NetBox",
    "New system- educational video V2 Sawal Jawab (Other)":           "New System Video - Other",
    "New system- educational video V2 Sawal Jawab (Payout)":          "New System Video - Payout",
    "PNM Releted":            "PNM Related",
    "Lead Releted":           "Lead Related",
    "Lead flow":              "Lead Flow",
    "PAYGt":                  "PayG Basic Understanding",
    "ISP recharge Proof":     "ISP Recharge Proof",
    "Want to Remove Lead":    "Lead Related",
    "300 Security":           "Rs300 Security Deposit",
    "Breach Fundamental Rule":"Fundamental Breach",
    "Recovery Rs50":          "Recovery - Rs50 Pickup",
    "50 Rupees on Recovery":  "Recovery - Rs50 Pickup",
    "New Project - 5 April Comms": "New Project Comms",
    "New Project- PayG Mumbai":    "PayG Mumbai - New Project",
}
def nc(c): return CAT_NORM.get(c.strip(), c.strip())
def pd(d):
    p = d.split("/"); return (int(p[2]), int(p[0]), int(p[1]))

# ── Fetch Sheet ───────────────────────────────────────────────────────────────
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

# ── Standardize verbatims using Claude API ────────────────────────────────────
def standardize_batch(batch):
    if not API_KEY:
        print("  No API key — skipping standardization")
        return [r['verbatim'] for r in batch]

    items = "\n".join([f"{i+1}. [{r['category']}] {r['verbatim']}" for i, r in enumerate(batch)])
    prompt = f"""Standardize these partner support call notes into clean professional English.
Rules:
- Max 15 words per item
- Remove caller numbers, agent names
- CX = Customer. Keep: PayG, ISP, PNM, NetBox, IVR, Lead, BDO, TDS, Rs amounts
- Write as a clear concise issue statement
- Return ONLY a valid JSON array of strings, same count, no markdown

Input:
{items}

JSON array:"""

    payload = json.dumps({
        "model":      "claude-3-haiku-20240307",
        "max_tokens": 2000,
        "messages":   [{"role": "user", "content": prompt}]
    }).encode()

    req2 = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )
    with urllib.request.urlopen(req2, timeout=60) as resp:
        result = json.loads(resp.read())
    txt = result['content'][0]['text'].strip()
    start = txt.find('['); end = txt.rfind(']') + 1
    return json.loads(txt[start:end])

print("Standardizing verbatims...")
BATCH = 25
results_map = {}
batches = [rows[i:i+BATCH] for i in range(0, len(rows), BATCH)]
for bi, batch in enumerate(batches):
    print(f"  Batch {bi+1}/{len(batches)}...")
    try:
        results = standardize_batch(batch)
        for j, r in enumerate(batch):
            results_map[bi*BATCH+j] = results[j] if j < len(results) else r['verbatim']
        time.sleep(0.5)
    except Exception as e:
        print(f"  Batch {bi+1} failed: {e} — using raw")
        for j, r in enumerate(batch):
            results_map[bi*BATCH+j] = r['verbatim']

for i, r in enumerate(rows):
    r['std'] = results_map.get(i, r['verbatim'])

print("Standardization done!")

# ── Build data structures ─────────────────────────────────────────────────────
DAY = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
MON = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

by_date = defaultdict(lambda: defaultdict(list))
for r in rows:
    by_date[r["date"]][r["category"]].append(r)

dates = sorted(by_date.keys(), key=pd)

# ── Build index.html data ─────────────────────────────────────────────────────
data = {}
for date in dates:
    p  = date.split("/")
    dt = datetime.date(int(p[2]), int(p[0]), int(p[1]))
    total = sum(len(v) for v in by_date[date].values())
    cats  = sorted(by_date[date].items(), key=lambda x: -len(x[1]))
    data[date] = {
        "total":   total,
        "display": f"{DAY[dt.weekday()]}, {p[1]} {MON[int(p[0])]}",
        "day":     DAY[dt.weekday()],
        "dd":      p[1],
        "mm":      MON[int(p[0])],
        "categories": [{
            "name":    cat,
            "count":   len(recs),
            "pct":     round(len(recs) / total * 100, 1),
            "records": [{"v": r["std"], "p": (r["priority"] or "NA").replace("#N/A","NA"), "partner": r["partner"]} for r in recs]
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

# ── Build management data ─────────────────────────────────────────────────────
mgmt_daily = {}
for date in dates:
    p  = date.split("/")
    dt = datetime.date(int(p[2]), int(p[0]), int(p[1]))
    total = sum(len(v) for v in by_date[date].values())
    cats  = sorted(by_date[date].items(), key=lambda x: -len(x[1]))
    prio_counts = {'HH':0,'HL':0,'LH':0,'LL':0,'NA':0}
    for cat, recs in cats:
        for rec in recs:
            p2 = (rec['priority'] or 'NA').replace('#N/A','NA').strip() or 'NA'
            if p2 in prio_counts: prio_counts[p2] += 1
            else: prio_counts['NA'] += 1
    mgmt_daily[date] = {
        'total':   total,
        'display': f"{DAY[dt.weekday()]}, {p[1]} {MON[int(p[0])]}",
        'day':     DAY[dt.weekday()], 'dd': p[1], 'mm': MON[int(p[0])],
        'prio':    prio_counts,
        'categories': [{
            'name':    cat,
            'count':   len(recs),
            'pct':     round(len(recs)/total*100, 1),
            'records': [{'v': r['std'], 'p': (r['priority'] or 'NA').replace('#N/A','NA').strip() or 'NA', 'partner': r['partner']} for r in recs]
        } for cat, recs in cats]
    }

overall_prio = {'HH':0,'HL':0,'LH':0,'LL':0,'NA':0}
for r in rows:
    p2 = (r['priority'] or 'NA').replace('#N/A','NA').strip() or 'NA'
    if p2 in overall_prio: overall_prio[p2] += 1
    else: overall_prio['NA'] += 1

cat_totals = defaultdict(int)
for r in rows: cat_totals[r['category']] += 1
partner_totals = defaultdict(int)
for r in rows:
    if r['partner'] and r['partner'] not in ['#N/A','']:
        partner_totals[r['partner']] += 1

mgmt_data = {
    'dates':        dates,
    'daily':        mgmt_daily,
    'trend': {
        'dates':  [f"{mgmt_daily[d]['dd']} {mgmt_daily[d]['mm'][:3]}" for d in dates],
        'totals': [mgmt_daily[d]['total'] for d in dates],
        'HH':     [mgmt_daily[d]['prio']['HH'] for d in dates],
        'HL':     [mgmt_daily[d]['prio']['HL'] for d in dates],
        'LH':     [mgmt_daily[d]['prio']['LH'] for d in dates],
        'LL':     [mgmt_daily[d]['prio']['LL'] for d in dates],
    },
    'top_cats':     sorted(cat_totals.items(), key=lambda x:-x[1]),
    'top_partners': sorted(partner_totals.items(), key=lambda x:-x[1])[:15],
    'overall_prio': overall_prio,
    'total':        len(rows),
}

# ── Build index.html ──────────────────────────────────────────────────────────
with open("template.html", encoding="utf-8") as f:
    tmpl = f.read()

html = tmpl.replace("__DATA__",    json.dumps(data,  ensure_ascii=False))
html = html.replace("__MATRIX__",  json.dumps(mdata, ensure_ascii=False))
html = html.replace("__UPDATED__", now)
html = html.replace("__TOTAL__",   str(len(rows)))
html = html.replace("__DAYS__",    str(len(dates)))

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"index.html built!")

# ── Build management_dashboard.html ──────────────────────────────────────────
with open("mgmt_template.html", encoding="utf-8") as f:
    mgmt_tmpl = f.read()

mgmt_html = mgmt_tmpl.replace("__MGMT_DATA__", json.dumps(mgmt_data, ensure_ascii=False))
mgmt_html = mgmt_html.replace("__UPDATED__", now)
mgmt_html = mgmt_html.replace("__TOTAL__", str(len(rows)))
mgmt_html = mgmt_html.replace("__DAYS__", str(len(dates)))

with open("management_dashboard.html", "w", encoding="utf-8") as f:
    f.write(mgmt_html)
print(f"management_dashboard.html built!")

print(f"\nDone! {len(rows)} rows, {len(dates)} dates, updated {now}")
