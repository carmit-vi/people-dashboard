import json, urllib.request, base64, collections, os
from datetime import datetime, date

API_KEY   = os.environ.get("BAMBOOHR_API_KEY", "c15b1c6ef2e4b92b415b191b31fee9bc72158774")
SUBDOMAIN = "vi"
BASE_URL  = f"https://api.bamboohr.com/api/gateway.php/{SUBDOMAIN}/v1"

def api_get(path, data=None):
    creds   = base64.b64encode(f"{API_KEY}:x".encode()).decode()
    headers = {"Accept": "application/json", "Authorization": f"Basic {creds}"}
    if data:
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE_URL+path, data=json.dumps(data).encode(), headers=headers)
    else:
        req = urllib.request.Request(BASE_URL+path, headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

print("Fetching data from BambooHR...")
report = api_get("/reports/custom?format=json", {
    "title": "Board Dashboard",
    "filters": {"lastChanged": {"includeNull": "yes", "value": "2019-01-01"}},
    "fields": ["firstName","lastName","department","division","location",
               "hireDate","terminationDate","employmentHistoryStatus",
               "status","gender","age","jobTitle","4314","4313"]
})
employees = report.get("employees", [])

def pd(s):
    if not s or s == "0000-00-00": return None
    try: return datetime.strptime(s, "%Y-%m-%d").date()
    except: return None

for e in employees:
    e["hd"]      = pd(e.get("hireDate"))
    e["td"]      = pd(e.get("terminationDate"))
    e["ttype"]   = e.get("4313","") or ""
    e["treason"] = e.get("4314","") or ""

# Exclude data inconsistencies (Active status but Terminated employment history, or missing dept+status)
active = [e for e in employees
          if e["status"] == "Active"
          and e.get("employmentHistoryStatus","") not in ("Terminated",)
          and e.get("department")]

terminated = [e for e in employees if e["status"] == "Inactive" and e["td"]]
today = date.today()
CY    = today.year
years = list(range(2020, CY + 1))

def hc_at(d):
    return sum(1 for e in employees
               if e["hd"] and e["hd"] <= d
               and (not e["td"] or e["td"] > d)
               and e.get("employmentHistoryStatus","") not in ("Terminated",)
               and e.get("department"))

def q_label(m):
    return f"Q{(m-1)//3+1}"

# ── Annual stats ──────────────────────────────────────────────
yearly = {}
for y in years:
    h   = [e for e in employees  if e["hd"] and e["hd"].year == y]
    t   = [e for e in terminated if e["td"] and e["td"].year == y]
    vol = [x for x in t if "Voluntary"   in x["ttype"]]
    inv = [x for x in t if "Involuntary" in x["ttype"]]
    jan1  = date(y, 1, 1)
    dec31 = date(y, 12, 31) if y < CY else today
    avg   = (hc_at(jan1) + hc_at(dec31)) / 2 or 1
    yearly[y] = {
        "hires": len(h), "terms": len(t), "vol": len(vol), "inv": len(inv),
        "hc": hc_at(dec31), "turnover": round(len(t)/avg*100, 1)
    }

# ── Quarterly data (all years) ────────────────────────────────
# Build: { "2024-Q1": {hires, terms, vol, inv, reasons_vol, reasons_inv} }
quarterly = {}
for y in years:
    for q in range(1, 5):
        months = [(q-1)*3+1, (q-1)*3+2, (q-1)*3+3]
        key = f"{y}-Q{q}"
        h = [e for e in employees  if e["hd"] and e["hd"].year==y and e["hd"].month in months]
        t = [e for e in terminated if e["td"] and e["td"].year==y and e["td"].month in months]
        vol = [x for x in t if "Voluntary"   in x["ttype"]]
        inv = [x for x in t if "Involuntary" in x["ttype"]]
        vol_r = dict(collections.Counter(x["treason"] for x in vol if x["treason"]).most_common(6))
        inv_r = dict(collections.Counter(x["treason"] for x in inv if x["treason"]).most_common(6))
        exits_detail = [{"name": f"{x['firstName']} {x['lastName']}",
                         "dept": x.get("department","") or "",
                         "date": str(x["td"]),
                         "type": x["ttype"],
                         "reason": x["treason"]} for x in t]
        hires_detail = [{"name": f"{x['firstName']} {x['lastName']}",
                         "dept": x.get("department","") or "",
                         "date": str(x["hd"])} for x in h]
        quarterly[key] = {
            "hires": len(h), "terms": len(t),
            "vol": len(vol), "inv": len(inv),
            "vol_reasons": vol_r, "inv_reasons": inv_r,
            "exits_detail": exits_detail,
            "hires_detail": hires_detail,
        }

# ── Breakdowns ────────────────────────────────────────────────
tenures    = [(today - e["hd"]).days / 365.25 for e in active if e["hd"]]
avg_tenure = round(sum(tenures)/len(tenures), 1) if tenures else 0
tbuckets   = {"< 1 yr": sum(1 for t in tenures if t < 1),
              "1-2 yrs": sum(1 for t in tenures if 1 <= t < 2),
              "2-4 yrs": sum(1 for t in tenures if 2 <= t < 4),
              "4+ yrs":  sum(1 for t in tenures if t >= 4)}

dept   = dict(sorted(collections.Counter(e["department"] for e in active).items(), key=lambda x: -x[1])[:10])
loc    = dict(collections.Counter(e["location"]  for e in active if e["location"]).most_common())
gen    = dict(collections.Counter(e["gender"]    for e in active if e["gender"]))
div    = dict(collections.Counter(e["division"]  for e in active if e["division"]).most_common())

recent = [e for e in terminated if e["td"] and e["td"].year >= 2023]
vol_r_all = dict(collections.Counter(e["treason"] for e in recent if "Voluntary"   in e["ttype"] and e["treason"]).most_common(7))
inv_r_all = dict(collections.Counter(e["treason"] for e in recent if "Involuntary" in e["ttype"] and e["treason"]).most_common(7))

monthly = {}
for y in [CY-1, CY]:
    for m in range(1, 13):
        k = f"{y}-{m:02d}"
        monthly[k] = {
            "h": sum(1 for e in employees  if e["hd"] and e["hd"].year==y and e["hd"].month==m),
            "t": sum(1 for e in terminated if e["td"] and e["td"].year==y and e["td"].month==m)
        }

curr_y = yearly.get(CY, {})
ml = list(monthly.keys())
mh = [monthly[k]["h"] for k in ml]
mt = [monthly[k]["t"] for k in ml]

def build_rows(yearly, years):
    rows = []
    for y in years:
        d    = yearly[y]
        net  = d["hires"] - d["terms"]
        sign = "+" if net >= 0 else ""
        col  = "var(--green)" if net >= 0 else "var(--red)"
        pill = "pill-amber" if d["turnover"] > 30 else "pill-blue"
        rows.append(
            f'<tr><td class="num">{y}</td><td class="num">{d["hc"]}</td>'
            f'<td><span class="pill pill-green">+{d["hires"]}</span></td>'
            f'<td class="num">{d["terms"]}</td>'
            f'<td><span class="pill pill-orange">{d["vol"]}</span></td>'
            f'<td><span class="pill pill-red">{d["inv"]}</span></td>'
            f'<td><span class="pill {pill}">{d["turnover"]}%</span></td>'
            f'<td class="num" style="color:{col}">{sign}{net}</td></tr>'
        )
    return "\n".join(rows)

# ── Serialize JS data ─────────────────────────────────────────
QUARTERLY_JS = json.dumps(quarterly)
YEARS_JS     = json.dumps([str(y) for y in years])
HC_JS        = json.dumps([yearly[y]["hc"]       for y in years])
HIRES_JS     = json.dumps([yearly[y]["hires"]    for y in years])
TERMS_JS     = json.dumps([yearly[y]["terms"]    for y in years])
VOL_JS       = json.dumps([yearly[y]["vol"]      for y in years])
INV_JS       = json.dumps([yearly[y]["inv"]      for y in years])
TURNOVER_JS  = json.dumps([yearly[y]["turnover"] for y in years])
ML_JS        = json.dumps(ml)
MH_JS        = json.dumps(mh)
MT_JS        = json.dumps(mt)
DEPT_L_JS    = json.dumps(list(dept.keys()))
DEPT_V_JS    = json.dumps(list(dept.values()))
LOC_L_JS     = json.dumps(list(loc.keys()))
LOC_V_JS     = json.dumps(list(loc.values()))
GEN_L_JS     = json.dumps(list(gen.keys()))
GEN_V_JS     = json.dumps(list(gen.values()))
TEN_V_JS     = json.dumps(list(tbuckets.values()))
DIV_L_JS     = json.dumps(list(div.keys()))
DIV_V_JS     = json.dumps(list(div.values()))
VR_L_JS      = json.dumps(list(vol_r_all.keys()))
VR_V_JS      = json.dumps(list(vol_r_all.values()))
IR_L_JS      = json.dumps(list(inv_r_all.keys()))
IR_V_JS      = json.dumps(list(inv_r_all.values()))
TABLE_ROWS   = build_rows(yearly, years)
TODAY_STR    = today.strftime("%d %b %Y")
TODAY_LONG   = today.strftime("%d %B %Y")
ACTIVE_COUNT = len(active)
TERM_COUNT   = len(terminated)

# ── Generate HTML ─────────────────────────────────────────────
html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>People Analytics — vi.co</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#F5F6FA;--surface:#FFFFFF;--border:#E2E5EF;--text-primary:#0F1629;--text-secondary:#5A6478;--text-muted:#94A3B8;--blue:#4338CA;--green:#059669;--red:#DC2626;--orange:#7C3AED;--purple:#3730A3;--teal:#0891B2;--amber:#64748B;--rose:#BE185D;--indigo:#818CF8;--pink:#A5B4FC;--lime:#6366F1;--sky:#C7D2FE;--blue-bg:#EEF2FF;--green-bg:#ECFDF5;--red-bg:#FEF2F2;--orange-bg:#F5F3FF;--amber-bg:#F8FAFC;--radius:12px;--radius-sm:8px;--shadow-sm:0 1px 3px rgba(67,56,202,.08),0 1px 2px rgba(67,56,202,.04)}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Plus Jakarta Sans','Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text-primary);font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:24px 40px;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:20px;font-weight:800;letter-spacing:-.4px}
.header p{font-size:13px;color:var(--text-secondary);margin-top:2px}
.badge{background:var(--blue-bg);color:var(--blue);border:1px solid #C7D2FE;border-radius:20px;padding:5px 14px;font-size:12px;font-weight:600}
.container{max-width:1360px;margin:0 auto;padding:32px 40px}
.section-label{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--text-muted);margin-bottom:14px;margin-top:36px}
.section-label:first-child{margin-top:0}
.kpi-grid{display:grid;grid-template-columns:repeat(8,1fr);gap:12px;margin-bottom:8px}
@media(max-width:1200px){.kpi-grid{grid-template-columns:repeat(4,1fr)}}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px 18px;box-shadow:var(--shadow-sm);position:relative;overflow:hidden}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:var(--radius) var(--radius) 0 0}
.kpi.blue::before{background:var(--blue)}.kpi.green::before{background:var(--green)}.kpi.red::before{background:var(--red)}.kpi.orange::before{background:var(--orange)}.kpi.purple::before{background:var(--purple)}.kpi.amber::before{background:var(--amber)}.kpi.teal::before{background:var(--teal)}.kpi.rose::before{background:var(--rose)}
.kpi-value{font-size:32px;font-weight:800;line-height:1;letter-spacing:-1px}
.kpi.blue .kpi-value{color:#4338CA}.kpi.green .kpi-value{color:#059669}.kpi.red .kpi-value{color:#DC2626}.kpi.orange .kpi-value{color:#818CF8}.kpi.purple .kpi-value{color:#3730A3}.kpi.amber .kpi-value{color:#64748B}.kpi.teal .kpi-value{color:#0891B2}.kpi.rose .kpi-value{color:#6366F1}
.kpi-label{font-size:12px;font-weight:600;color:var(--text-secondary);margin-top:6px}
.kpi-sub{font-size:11px;color:var(--text-muted);margin-top:2px}
.grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-bottom:16px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:16px}
.grid-1{display:grid;grid-template-columns:1fr;gap:16px;margin-bottom:16px}
@media(max-width:1100px){.grid-3{grid-template-columns:repeat(2,1fr)}}
@media(max-width:800px){.grid-2,.grid-3{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;box-shadow:var(--shadow-sm)}
.card-title{font-size:13px;font-weight:700;color:var(--text-primary);margin-bottom:20px;display:flex;align-items:center;gap:8px}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot-blue{background:var(--blue)}.dot-green{background:var(--green)}.dot-red{background:var(--red)}.dot-orange{background:var(--orange)}.dot-purple{background:var(--purple)}.dot-amber{background:var(--amber)}.dot-teal{background:var(--teal)}.dot-indigo{background:var(--indigo)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{background:var(--bg);color:var(--text-muted);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;padding:10px 16px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap}
tbody td{padding:11px 16px;border-bottom:1px solid var(--border)}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--bg)}
.num{font-weight:700}
.pill{display:inline-flex;align-items:center;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;white-space:nowrap}
.pill-green{background:#ECFDF5;color:#059669;border:1px solid #A7F3D0}
.pill-red{background:#FEF2F2;color:#DC2626;border:1px solid #FECACA}
.pill-orange{background:#EEF2FF;color:#818CF8;border:1px solid #C7D2FE}
.pill-blue{background:#EEF2FF;color:#4338CA;border:1px solid #C7D2FE}
.pill-amber{background:#EEF2FF;color:#6366F1;border:1px solid #C7D2FE}
.pill-purple{background:#EEF2FF;color:#3730A3;border:1px solid #A5B4FC}
.alert{background:#FFFBEB;border:1px solid #FDE68A;border-left:4px solid var(--amber);border-radius:var(--radius-sm);padding:14px 18px;margin-bottom:16px;display:flex;align-items:flex-start;gap:12px}
.alert-icon{font-size:18px;flex-shrink:0;margin-top:1px}
.alert-text{font-size:13px;color:#92400E;line-height:1.7}
.alert-text strong{color:#78350F;font-weight:700}
/* ── Quarterly filter UI ── */
.q-controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px;padding:16px 20px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow-sm)}
.q-controls label{font-size:12px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em}
.q-select{font-family:inherit;font-size:13px;font-weight:600;border:1px solid var(--border);border-radius:8px;padding:7px 12px;background:var(--bg);color:var(--text-primary);cursor:pointer;outline:none}
.q-select:focus{border-color:var(--blue)}
.q-btn-group{display:flex;gap:6px}
.q-btn{font-family:inherit;font-size:12px;font-weight:700;border:1px solid var(--border);border-radius:8px;padding:7px 16px;background:var(--bg);color:var(--text-secondary);cursor:pointer;transition:all .15s}
.q-btn:hover{border-color:var(--blue);color:var(--blue)}
.q-btn.active{background:#4338CA;border-color:#4338CA;color:#fff}
.q-summary{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
.q-stat{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;text-align:center}
.q-stat-value{font-size:28px;font-weight:800;letter-spacing:-1px}
.q-stat-label{font-size:11px;color:var(--text-secondary);font-weight:600;margin-top:4px}
.q-panel{display:none}
.q-panel.visible{display:block}
.detail-table tbody td{padding:9px 14px;font-size:12px}
.footer{text-align:center;padding:32px 0 24px;font-size:12px;color:var(--text-muted);border-top:1px solid var(--border);margin-top:40px}
</style>
</head>
<body>
<header class="header">
  <div>
    <h1>People Analytics Dashboard</h1>
    <p>vi.co &nbsp;&middot;&nbsp; Updated """ + TODAY_STR + """ &nbsp;&middot;&nbsp; Source: BambooHR</p>
  </div>
  <div class="badge">Auto-updated monthly</div>
</header>
<main class="container">

  <!-- KPIs -->
  <div class="section-label">Key Metrics &mdash; """ + str(CY) + """ YTD</div>
  <div class="kpi-grid">
    <div class="kpi blue"><div class="kpi-value">""" + str(ACTIVE_COUNT) + """</div><div class="kpi-label">Active Headcount</div><div class="kpi-sub">As of today</div></div>
    <div class="kpi green"><div class="kpi-value">""" + str(curr_y.get("hires",0)) + """</div><div class="kpi-label">New Hires """ + str(CY) + """</div><div class="kpi-sub">YTD</div></div>
    <div class="kpi red"><div class="kpi-value">""" + str(curr_y.get("terms",0)) + """</div><div class="kpi-label">Total Exits """ + str(CY) + """</div><div class="kpi-sub">YTD</div></div>
    <div class="kpi orange"><div class="kpi-value">""" + str(curr_y.get("vol",0)) + """</div><div class="kpi-label">Voluntary """ + str(CY) + """</div><div class="kpi-sub">Resignations</div></div>
    <div class="kpi rose"><div class="kpi-value">""" + str(curr_y.get("inv",0)) + """</div><div class="kpi-label">Involuntary """ + str(CY) + """</div><div class="kpi-sub">Terminations</div></div>
    <div class="kpi amber"><div class="kpi-value">""" + str(curr_y.get("turnover",0)) + """%</div><div class="kpi-label">Turnover Rate """ + str(CY) + """</div><div class="kpi-sub">Exits / Avg HC</div></div>
    <div class="kpi purple"><div class="kpi-value">""" + str(avg_tenure) + """</div><div class="kpi-label">Avg. Tenure</div><div class="kpi-sub">Years (active)</div></div>
    <div class="kpi teal"><div class="kpi-value">""" + str(TERM_COUNT) + """</div><div class="kpi-label">All-Time Exits</div><div class="kpi-sub">Historical total</div></div>
  </div>

  <div class="alert">
    <div class="alert-icon">&#9888;</div>
    <div class="alert-text">
      <strong>2025 &mdash; Major Restructuring Year:</strong>
      49 exits of which 40 were involuntary terminations (82%), driving a 45.2% Turnover Rate.
      16 layoffs occurred on a single day (Feb 7) &mdash; primarily from Transform R&amp;D.<br>
      <strong>In 2025&ndash;2026 the company strategically adopted AI tools, enabling leaner operations and directly driving workforce restructuring.</strong>
    </div>
  </div>

  <!-- ══ QUARTERLY DRILL-DOWN ══════════════════════════════════ -->
  <div class="section-label">Quarterly Breakdown</div>
  <div class="q-controls">
    <label>Year</label>
    <select class="q-select" id="qYear" onchange="renderQuarter()">""" + "".join(f'<option value="{y}" {"selected" if y==CY else ""}>{y}</option>' for y in reversed(years)) + """</select>
    <label style="margin-left:8px">Quarter</label>
    <div class="q-btn-group" id="qBtns">
      <button class="q-btn active" data-q="all" onclick="setQ('all')">All Year</button>
      <button class="q-btn" data-q="Q1" onclick="setQ('Q1')">Q1</button>
      <button class="q-btn" data-q="Q2" onclick="setQ('Q2')">Q2</button>
      <button class="q-btn" data-q="Q3" onclick="setQ('Q3')">Q3</button>
      <button class="q-btn" data-q="Q4" onclick="setQ('Q4')">Q4</button>
    </div>
  </div>

  <!-- Summary stats -->
  <div class="q-summary" id="qSummary"></div>

  <!-- Charts row -->
  <div class="grid-2" id="qCharts">
    <div class="card">
      <div class="card-title"><span class="dot dot-green"></span><span id="qChartTitle1">Quarterly Hires vs. Exits</span></div>
      <div style="height:240px"><canvas id="cQ1"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title"><span class="dot dot-orange"></span><span id="qChartTitle2">Quarterly Voluntary vs. Involuntary</span></div>
      <div style="height:240px"><canvas id="cQ2"></canvas></div>
    </div>
  </div>

  <!-- Exit reasons -->
  <div class="grid-2">
    <div class="card">
      <div class="card-title"><span class="dot dot-orange"></span>Voluntary Exit Reasons</div>
      <div style="height:220px"><canvas id="cQVR"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title"><span class="dot dot-red"></span>Involuntary Exit Reasons</div>
      <div style="height:220px"><canvas id="cQIR"></canvas></div>
    </div>
  </div>

  <!-- Detail tables -->
  <div class="grid-2">
    <div class="card">
      <div class="card-title"><span class="dot dot-red"></span>Exits Detail</div>
      <div class="table-wrap" style="max-height:320px;overflow-y:auto">
        <table class="detail-table">
          <thead><tr><th>Date</th><th>Name</th><th>Department</th><th>Type</th><th>Reason</th></tr></thead>
          <tbody id="qExitsBody"></tbody>
        </table>
      </div>
    </div>
    <div class="card">
      <div class="card-title"><span class="dot dot-green"></span>Hires Detail</div>
      <div class="table-wrap" style="max-height:320px;overflow-y:auto">
        <table class="detail-table">
          <thead><tr><th>Date</th><th>Name</th><th>Department</th></tr></thead>
          <tbody id="qHiresBody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ══ ANNUAL TRENDS ══════════════════════════════════════════ -->
  <div class="section-label">Annual Trends</div>
  <div class="grid-2">
    <div class="card"><div class="card-title"><span class="dot dot-blue"></span>Year-End Headcount</div><div style="height:240px"><canvas id="cHC"></canvas></div></div>
    <div class="card"><div class="card-title"><span class="dot dot-green"></span>New Hires vs. Exits by Year</div><div style="height:240px"><canvas id="cHT"></canvas></div></div>
  </div>
  <div class="grid-2">
    <div class="card"><div class="card-title"><span class="dot dot-amber"></span>Annual Turnover Rate (%)</div><div style="height:240px"><canvas id="cTO"></canvas></div></div>
    <div class="card"><div class="card-title"><span class="dot dot-orange"></span>Voluntary vs. Involuntary Exits</div><div style="height:240px"><canvas id="cVI"></canvas></div></div>
  </div>

  <div class="section-label">Monthly Trend (""" + str(CY-1) + """&ndash;""" + str(CY) + """)</div>
  <div class="grid-1">
    <div class="card"><div class="card-title"><span class="dot dot-blue"></span>Monthly Hires vs. Exits</div><div style="height:260px"><canvas id="cMon"></canvas></div></div>
  </div>

  <!-- ══ WORKFORCE BREAKDOWN ════════════════════════════════════ -->
  <div class="section-label">Workforce Breakdown</div>
  <div class="grid-3">
    <div class="card"><div class="card-title"><span class="dot dot-blue"></span>Headcount by Department</div><div style="height:280px"><canvas id="cDept"></canvas></div></div>
    <div class="card"><div class="card-title"><span class="dot dot-teal"></span>Headcount by Location</div><div style="height:280px"><canvas id="cLoc"></canvas></div></div>
    <div class="card"><div class="card-title"><span class="dot dot-purple"></span>Gender Distribution</div><div style="height:280px"><canvas id="cGen"></canvas></div></div>
  </div>
  <div class="grid-2">
    <div class="card"><div class="card-title"><span class="dot dot-green"></span>Tenure Distribution</div><div style="height:220px"><canvas id="cTen"></canvas></div></div>
    <div class="card"><div class="card-title"><span class="dot dot-indigo"></span>Headcount by Division</div><div style="height:220px"><canvas id="cDiv"></canvas></div></div>
  </div>

  <!-- ══ ALL-TIME EXIT REASONS ══════════════════════════════════ -->
  <div class="section-label">Exit Reasons — All Time (2023&ndash;""" + str(CY) + """)</div>
  <div class="grid-2">
    <div class="card"><div class="card-title"><span class="dot dot-orange"></span>Voluntary Exit Reasons</div><div style="height:240px"><canvas id="cVR"></canvas></div></div>
    <div class="card"><div class="card-title"><span class="dot dot-red"></span>Involuntary Exit Reasons</div><div style="height:240px"><canvas id="cIR"></canvas></div></div>
  </div>

  <!-- ══ ANNUAL TABLE ═══════════════════════════════════════════ -->
  <div class="section-label">Annual Summary Table</div>
  <div class="card" style="padding:0;overflow:hidden">
    <div class="table-wrap"><table>
      <thead><tr><th>Year</th><th>Headcount</th><th>New Hires</th><th>Total Exits</th><th>Voluntary</th><th>Involuntary</th><th>Turnover Rate</th><th>Net Change</th></tr></thead>
      <tbody>""" + TABLE_ROWS + """</tbody>
    </table></div>
  </div>

</main>
<footer class="footer">
  vi.co People Analytics &nbsp;&middot;&nbsp; Source: BambooHR &nbsp;&middot;&nbsp; Turnover = Exits / Avg Headcount &nbsp;&middot;&nbsp; """ + TODAY_LONG + """
</footer>

<script>
const C={blue:'#4338CA',green:'#059669',red:'#DC2626',orange:'#7C3AED',purple:'#3730A3',teal:'#0891B2',amber:'#64748B',rose:'#818CF8',indigo:'#6366F1',pink:'#A5B4FC',lime:'#C7D2FE',sky:'#94A3B8'};
const PAL=['#3730A3','#4338CA','#6366F1','#818CF8','#A5B4FC','#C7D2FE','#64748B','#94A3B8','#059669','#0891B2','#7C3AED','#DC2626'];
Chart.defaults.font.family="'Plus Jakarta Sans','Segoe UI',system-ui,sans-serif";
Chart.defaults.font.size=12;Chart.defaults.color='#6B7280';Chart.defaults.borderColor='#E8ECF0';
Chart.defaults.plugins.legend.labels.usePointStyle=true;Chart.defaults.plugins.legend.labels.padding=16;

// ── Quarterly data ────────────────────────────────────────────
const QDATA = """ + QUARTERLY_JS + """;
let currentQ = 'all';
let qChart1, qChart2, qChartVR, qChartIR;

function setQ(q) {
  currentQ = q;
  document.querySelectorAll('.q-btn').forEach(b => b.classList.toggle('active', b.dataset.q === q));
  renderQuarter();
}

function getQKeys(year, q) {
  if (q === 'all') return ['Q1','Q2','Q3','Q4'].map(qq => year+'-'+qq);
  return [year+'-'+q];
}

function mergeQ(keys) {
  const merged = {hires:0,terms:0,vol:0,inv:0,vol_reasons:{},inv_reasons:{},exits_detail:[],hires_detail:[]};
  keys.forEach(k => {
    const d = QDATA[k] || {};
    merged.hires += d.hires||0; merged.terms += d.terms||0;
    merged.vol   += d.vol||0;   merged.inv   += d.inv||0;
    Object.entries(d.vol_reasons||{}).forEach(([r,c])=>merged.vol_reasons[r]=(merged.vol_reasons[r]||0)+c);
    Object.entries(d.inv_reasons||{}).forEach(([r,c])=>merged.inv_reasons[r]=(merged.inv_reasons[r]||0)+c);
    (d.exits_detail||[]).forEach(x=>merged.exits_detail.push(x));
    (d.hires_detail||[]).forEach(x=>merged.hires_detail.push(x));
  });
  return merged;
}

function renderQuarter() {
  const year = document.getElementById('qYear').value;
  const q    = currentQ;

  // Summary stats
  if (q === 'all') {
    const qs  = ['Q1','Q2','Q3','Q4'];
    const hires = qs.map(qq => (QDATA[year+'-'+qq]||{}).hires||0);
    const terms = qs.map(qq => (QDATA[year+'-'+qq]||{}).terms||0);
    const vols  = qs.map(qq => (QDATA[year+'-'+qq]||{}).vol||0);
    const invs  = qs.map(qq => (QDATA[year+'-'+qq]||{}).inv||0);
    const net   = hires.reduce((a,b)=>a+b,0) - terms.reduce((a,b)=>a+b,0);
    const netSign = net>=0?'+':'';
    const netCol  = net>=0?C.green:C.red;

    document.getElementById('qSummary').innerHTML =
      stat(hires.reduce((a,b)=>a+b,0), 'Total Hires', C.green) +
      stat(terms.reduce((a,b)=>a+b,0), 'Total Exits', C.red) +
      stat(vols.reduce((a,b)=>a+b,0),  'Voluntary',   C.orange) +
      stat(invs.reduce((a,b)=>a+b,0),  'Involuntary', C.rose) +
      stat(netSign+net, 'Net Change', netCol);

    // Bar chart by quarter
    renderChart1(qs.map(qq=>year+' '+qq), hires, terms);
    renderChart2(qs.map(qq=>year+' '+qq), vols,  invs);

    // Aggregate exit/hire details and reasons
    const all = mergeQ(qs.map(qq=>year+'-'+qq));
    renderReasons(all.vol_reasons, all.inv_reasons);
    renderTables(all.exits_detail, all.hires_detail);
  } else {
    const d = QDATA[year+'-'+q] || {};
    const net = (d.hires||0)-(d.terms||0);
    const netSign = net>=0?'+':'';
    const netCol  = net>=0?C.green:C.red;

    document.getElementById('qSummary').innerHTML =
      stat(d.hires||0, 'Hires',        C.green) +
      stat(d.terms||0, 'Exits',        C.red) +
      stat(d.vol||0,   'Voluntary',    C.orange) +
      stat(d.inv||0,   'Involuntary',  C.rose) +
      stat(netSign+net,'Net Change',   netCol);

    // Monthly breakdown within quarter
    const qMonths = {Q1:['Jan','Feb','Mar'],Q2:['Apr','May','Jun'],Q3:['Jul','Aug','Sep'],Q4:['Oct','Nov','Dec']};
    renderChart1(qMonths[q], [null,null,null],[null,null,null]); // placeholder — no monthly breakdown in data
    renderChart2(qMonths[q], [null,null,null],[null,null,null]);

    // Show full quarter bar
    renderChart1([q], [d.hires||0], [d.terms||0]);
    renderChart2([q], [d.vol||0],   [d.inv||0]);
    renderReasons(d.vol_reasons||{}, d.inv_reasons||{});
    renderTables(d.exits_detail||[], d.hires_detail||[]);
  }
}

function stat(val, label, color) {
  return '<div class="q-stat"><div class="q-stat-value" style="color:'+color+'">'+val+'</div><div class="q-stat-label">'+label+'</div></div>';
}

function renderChart1(labels, hires, terms) {
  if (qChart1) qChart1.destroy();
  qChart1 = new Chart('cQ1', {type:'bar',data:{labels,datasets:[
    {label:'New Hires',data:hires,backgroundColor:'#4338CA',borderRadius:4},
    {label:'Exits',    data:terms,backgroundColor:'#94A3B8',borderRadius:4}
  ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#EEF2FF'}}}}});
}
function renderChart2(labels, vol, inv) {
  if (qChart2) qChart2.destroy();
  qChart2 = new Chart('cQ2', {type:'bar',data:{labels,datasets:[
    {label:'Voluntary',  data:vol,backgroundColor:'#A5B4FC',borderRadius:4},
    {label:'Involuntary',data:inv,backgroundColor:'#3730A3',borderRadius:4}
  ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#EEF2FF'}}}}});
}
function renderReasons(vr, ir) {
  const vrL=Object.keys(vr), vrV=Object.values(vr);
  const irL=Object.keys(ir), irV=Object.values(ir);
  if (qChartVR) qChartVR.destroy();
  if (qChartIR) qChartIR.destroy();
  if (vrL.length) {
    qChartVR = new Chart('cQVR',{type:'bar',data:{labels:vrL,datasets:[{data:vrV,backgroundColor:'#818CF8',borderRadius:4,barThickness:16}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:'#EEF2FF'}},y:{grid:{display:false}}}}});
  } else {
    document.getElementById('cQVR').getContext('2d').clearRect(0,0,9999,9999);
  }
  if (irL.length) {
    qChartIR = new Chart('cQIR',{type:'bar',data:{labels:irL,datasets:[{data:irV,backgroundColor:'#3730A3',borderRadius:4,barThickness:16}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:'#EEF2FF'}},y:{grid:{display:false}}}}});
  } else {
    document.getElementById('cQIR').getContext('2d').clearRect(0,0,9999,9999);
  }
}
function typeLabel(t) {
  if (t.includes('Voluntary'))   return '<span class="pill pill-orange">Voluntary</span>';
  if (t.includes('Involuntary')) return '<span class="pill pill-red">Involuntary</span>';
  if (t.includes('Death'))       return '<span class="pill pill-purple">Death</span>';
  return '<span class="pill pill-blue">'+t+'</span>';
}
function renderTables(exits, hires) {
  document.getElementById('qExitsBody').innerHTML = exits.length
    ? exits.sort((a,b)=>a.date.localeCompare(b.date)).map(e =>
        '<tr><td>'+e.date+'</td><td class="num">'+e.name+'</td><td>'+e.dept+'</td><td>'+typeLabel(e.type)+'</td><td>'+e.reason+'</td></tr>'
      ).join('')
    : '<tr><td colspan="5" style="color:var(--text-muted);text-align:center;padding:20px">No exits in this period</td></tr>';

  document.getElementById('qHiresBody').innerHTML = hires.length
    ? hires.sort((a,b)=>a.date.localeCompare(b.date)).map(h =>
        '<tr><td>'+h.date+'</td><td class="num">'+h.name+'</td><td>'+h.dept+'</td></tr>'
      ).join('')
    : '<tr><td colspan="3" style="color:var(--text-muted);text-align:center;padding:20px">No hires in this period</td></tr>';
}

// Init quarterly
renderQuarter();

// ── Annual Charts ─────────────────────────────────────────────
const YRS=""" + YEARS_JS + """;
new Chart('cHC',{type:'line',data:{labels:YRS,datasets:[{label:'Headcount',data:""" + HC_JS + """,borderColor:'#4338CA',backgroundColor:'rgba(67,56,202,.08)',fill:true,tension:.4,borderWidth:2.5,pointRadius:4,pointBackgroundColor:'#4338CA',pointBorderColor:'#fff',pointBorderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:'#EEF2FF'}}}}});
new Chart('cHT',{type:'bar',data:{labels:YRS,datasets:[{label:'New Hires',data:""" + HIRES_JS + """,backgroundColor:'#4338CA',borderRadius:4},{label:'Exits',data:""" + TERMS_JS + """,backgroundColor:'#94A3B8',borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#EEF2FF'}}}}});
new Chart('cTO',{type:'line',data:{labels:YRS,datasets:[{label:'Turnover %',data:""" + TURNOVER_JS + """,borderColor:'#818CF8',backgroundColor:'rgba(129,140,248,.1)',fill:true,tension:.4,borderWidth:2.5,pointRadius:4,pointBackgroundColor:'#818CF8',pointBorderColor:'#fff',pointBorderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:'#EEF2FF'},ticks:{callback:v=>v+'%'}}}}});
new Chart('cVI',{type:'bar',data:{labels:YRS,datasets:[{label:'Voluntary',data:""" + VOL_JS + """,backgroundColor:'#A5B4FC',borderRadius:4},{label:'Involuntary',data:""" + INV_JS + """,backgroundColor:'#3730A3',borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#EEF2FF'}}}}});
new Chart('cMon',{type:'bar',data:{labels:""" + ML_JS + """,datasets:[{label:'New Hires',data:""" + MH_JS + """,backgroundColor:'#6366F1',borderRadius:3},{label:'Exits',data:""" + MT_JS + """,backgroundColor:'#94A3B8',borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#EEF2FF'}}}}});
new Chart('cDept',{type:'bar',data:{labels:""" + DEPT_L_JS + """,datasets:[{data:""" + DEPT_V_JS + """,backgroundColor:PAL,borderRadius:4,barThickness:18}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:'#EEF2FF'}},y:{grid:{display:false}}}}});
new Chart('cLoc',{type:'doughnut',data:{labels:""" + LOC_L_JS + """,datasets:[{data:""" + LOC_V_JS + """,backgroundColor:PAL,borderWidth:2,borderColor:'#fff',hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom',labels:{font:{size:11}}}}}});
new Chart('cGen',{type:'doughnut',data:{labels:""" + GEN_L_JS + """,datasets:[{data:""" + GEN_V_JS + """,backgroundColor:['#4338CA','#A5B4FC','#64748B'],borderWidth:2,borderColor:'#fff',hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom'}}}});
new Chart('cTen',{type:'bar',data:{labels:['< 1 yr','1-2 yrs','2-4 yrs','4+ yrs'],datasets:[{data:""" + TEN_V_JS + """,backgroundColor:['#C7D2FE','#818CF8','#6366F1','#3730A3'],borderRadius:6,barThickness:36}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#EEF2FF'}}}}});
new Chart('cDiv',{type:'doughnut',data:{labels:""" + DIV_L_JS + """,datasets:[{data:""" + DIV_V_JS + """,backgroundColor:PAL,borderWidth:2,borderColor:'#fff',hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom',labels:{font:{size:11}}}}}});
new Chart('cVR',{type:'bar',data:{labels:""" + VR_L_JS + """,datasets:[{data:""" + VR_V_JS + """,backgroundColor:'#818CF8',borderRadius:4,barThickness:18}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:'#EEF2FF'}},y:{grid:{display:false}}}}});
new Chart('cIR',{type:'bar',data:{labels:""" + IR_L_JS + """,datasets:[{data:""" + IR_V_JS + """,backgroundColor:'#3730A3',borderRadius:4,barThickness:18}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:'#EEF2FF'}},y:{grid:{display:false}}}}});
</script>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"Done — index.html generated ({TODAY_STR}), active: {ACTIVE_COUNT}")
