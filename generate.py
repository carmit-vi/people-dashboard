import json, urllib.request, base64, collections, os
from datetime import datetime, date

API_KEY   = os.environ["BAMBOOHR_API_KEY"]
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

active     = [e for e in employees if e["status"] == "Active"]
terminated = [e for e in employees if e["status"] == "Inactive" and e["td"]]
today      = date.today()
CY         = today.year
years      = list(range(2020, CY + 1))

def hires_y(y): return [e for e in employees  if e["hd"] and e["hd"].year == y]
def terms_y(y): return [e for e in terminated if e["td"] and e["td"].year == y]
def hc_at(d):
    return sum(1 for e in employees if e["hd"] and e["hd"] <= d and (not e["td"] or e["td"] > d))

yearly = {}
for y in years:
    h = hires_y(y); t = terms_y(y)
    vol  = [x for x in t if "Voluntary"   in x["ttype"]]
    inv  = [x for x in t if "Involuntary" in x["ttype"]]
    jan1  = date(y, 1, 1)
    dec31 = date(y, 12, 31) if y < CY else today
    avg   = (hc_at(jan1) + hc_at(dec31)) / 2 or 1
    yearly[y] = {"hires": len(h), "terms": len(t), "vol": len(vol), "inv": len(inv),
                 "hc": hc_at(dec31), "turnover": round(len(t)/avg*100, 1)}

tenures    = [(today - e["hd"]).days / 365.25 for e in active if e["hd"]]
avg_tenure = round(sum(tenures)/len(tenures), 1) if tenures else 0
tbuckets   = {"< 1 yr": sum(1 for t in tenures if t < 1),
              "1-2 yrs": sum(1 for t in tenures if 1 <= t < 2),
              "2-4 yrs": sum(1 for t in tenures if 2 <= t < 4),
              "4+ yrs":  sum(1 for t in tenures if t >= 4)}

dept   = dict(sorted(collections.Counter(e["department"] for e in active if e["department"]).items(), key=lambda x: -x[1])[:10])
loc    = dict(collections.Counter(e["location"]  for e in active if e["location"]).most_common())
gen    = dict(collections.Counter(e["gender"]    for e in active if e["gender"]))
div    = dict(collections.Counter(e["division"]  for e in active if e["division"]).most_common())

recent = [e for e in terminated if e["td"] and e["td"].year >= 2023]
vol_r  = dict(collections.Counter(e["treason"] for e in recent if "Voluntary"   in e["ttype"] and e["treason"]).most_common(7))
inv_r  = dict(collections.Counter(e["treason"] for e in recent if "Involuntary" in e["ttype"] and e["treason"]).most_common(7))

monthly = {}
for y in [CY - 1, CY]:
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

YEARS_JS    = json.dumps([str(y) for y in years])
HC_JS       = json.dumps([yearly[y]["hc"]      for y in years])
HIRES_JS    = json.dumps([yearly[y]["hires"]   for y in years])
TERMS_JS    = json.dumps([yearly[y]["terms"]   for y in years])
VOL_JS      = json.dumps([yearly[y]["vol"]     for y in years])
INV_JS      = json.dumps([yearly[y]["inv"]     for y in years])
TURNOVER_JS = json.dumps([yearly[y]["turnover"]for y in years])
ML_JS       = json.dumps(ml)
MH_JS       = json.dumps(mh)
MT_JS       = json.dumps(mt)
DEPT_L_JS   = json.dumps(list(dept.keys()))
DEPT_V_JS   = json.dumps(list(dept.values()))
LOC_L_JS    = json.dumps(list(loc.keys()))
LOC_V_JS    = json.dumps(list(loc.values()))
GEN_L_JS    = json.dumps(list(gen.keys()))
GEN_V_JS    = json.dumps(list(gen.values()))
TEN_V_JS    = json.dumps(list(tbuckets.values()))
DIV_L_JS    = json.dumps(list(div.keys()))
DIV_V_JS    = json.dumps(list(div.values()))
VR_L_JS     = json.dumps(list(vol_r.keys()))
VR_V_JS     = json.dumps(list(vol_r.values()))
IR_L_JS     = json.dumps(list(inv_r.keys()))
IR_V_JS     = json.dumps(list(inv_r.values()))

TABLE_ROWS  = build_rows(yearly, years)
TODAY_STR   = today.strftime("%d %b %Y")
TODAY_LONG  = today.strftime("%d %B %Y")

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
:root{--bg:#F7F8FA;--surface:#FFFFFF;--border:#E8ECF0;--text-primary:#111827;--text-secondary:#6B7280;--text-muted:#9CA3AF;--blue:#2563EB;--green:#16A34A;--red:#DC2626;--orange:#EA580C;--purple:#7C3AED;--teal:#0D9488;--amber:#D97706;--rose:#E11D48;--indigo:#4F46E5;--pink:#DB2777;--blue-bg:#EFF6FF;--green-bg:#F0FDF4;--red-bg:#FEF2F2;--orange-bg:#FFF7ED;--amber-bg:#FFFBEB;--radius:12px;--radius-sm:8px;--shadow-sm:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04)}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Plus Jakarta Sans','Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text-primary);font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:24px 40px;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:20px;font-weight:800;letter-spacing:-.4px}
.header p{font-size:13px;color:var(--text-secondary);margin-top:2px}
.header-badge{background:var(--blue-bg);color:var(--blue);border:1px solid #BFDBFE;border-radius:20px;padding:5px 14px;font-size:12px;font-weight:600}
.container{max-width:1360px;margin:0 auto;padding:32px 40px}
.section-label{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--text-muted);margin-bottom:14px;margin-top:36px}
.section-label:first-child{margin-top:0}
.kpi-grid{display:grid;grid-template-columns:repeat(8,1fr);gap:12px;margin-bottom:8px}
@media(max-width:1200px){.kpi-grid{grid-template-columns:repeat(4,1fr)}}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px 18px;box-shadow:var(--shadow-sm);position:relative;overflow:hidden}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:var(--radius) var(--radius) 0 0}
.kpi.blue::before{background:var(--blue)}.kpi.green::before{background:var(--green)}.kpi.red::before{background:var(--red)}.kpi.orange::before{background:var(--orange)}.kpi.purple::before{background:var(--purple)}.kpi.amber::before{background:var(--amber)}.kpi.teal::before{background:var(--teal)}.kpi.rose::before{background:var(--rose)}
.kpi-value{font-size:32px;font-weight:800;line-height:1;letter-spacing:-1px}
.kpi.blue .kpi-value{color:var(--blue)}.kpi.green .kpi-value{color:var(--green)}.kpi.red .kpi-value{color:var(--red)}.kpi.orange .kpi-value{color:var(--orange)}.kpi.purple .kpi-value{color:var(--purple)}.kpi.amber .kpi-value{color:var(--amber)}.kpi.teal .kpi-value{color:var(--teal)}.kpi.rose .kpi-value{color:var(--rose)}
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
tbody td{padding:12px 16px;border-bottom:1px solid var(--border)}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--bg)}
.num{font-weight:700}
.pill{display:inline-flex;align-items:center;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;white-space:nowrap}
.pill-green{background:var(--green-bg);color:var(--green);border:1px solid #BBF7D0}
.pill-red{background:var(--red-bg);color:var(--red);border:1px solid #FECACA}
.pill-orange{background:var(--orange-bg);color:var(--orange);border:1px solid #FED7AA}
.pill-blue{background:var(--blue-bg);color:var(--blue);border:1px solid #BFDBFE}
.pill-amber{background:var(--amber-bg);color:var(--amber);border:1px solid #FDE68A}
.alert{background:#FFFBEB;border:1px solid #FDE68A;border-left:4px solid var(--amber);border-radius:var(--radius-sm);padding:14px 18px;margin-bottom:16px;display:flex;align-items:flex-start;gap:12px}
.alert-icon{font-size:18px;flex-shrink:0;margin-top:1px}
.alert-text{font-size:13px;color:#92400E;line-height:1.7}
.alert-text strong{color:#78350F;font-weight:700}
.footer{text-align:center;padding:32px 0 24px;font-size:12px;color:var(--text-muted);border-top:1px solid var(--border);margin-top:40px}
</style>
</head>
<body>
<header class="header">
  <div>
    <h1>People Analytics Dashboard</h1>
    <p>vi.co &nbsp;&middot;&nbsp; Updated """ + TODAY_STR + """ &nbsp;&middot;&nbsp; Source: BambooHR</p>
  </div>
  <div class="header-badge">Auto-updated monthly</div>
</header>
<main class="container">
  <div class="section-label">Key Metrics &mdash; """ + str(CY) + """ YTD</div>
  <div class="kpi-grid">
    <div class="kpi blue"><div class="kpi-value">""" + str(len(active)) + """</div><div class="kpi-label">Active Headcount</div><div class="kpi-sub">As of today</div></div>
    <div class="kpi green"><div class="kpi-value">""" + str(curr_y.get("hires",0)) + """</div><div class="kpi-label">New Hires &mdash; """ + str(CY) + """</div><div class="kpi-sub">YTD</div></div>
    <div class="kpi red"><div class="kpi-value">""" + str(curr_y.get("terms",0)) + """</div><div class="kpi-label">Total Exits &mdash; """ + str(CY) + """</div><div class="kpi-sub">YTD</div></div>
    <div class="kpi orange"><div class="kpi-value">""" + str(curr_y.get("vol",0)) + """</div><div class="kpi-label">Voluntary &mdash; """ + str(CY) + """</div><div class="kpi-sub">Resignations YTD</div></div>
    <div class="kpi rose"><div class="kpi-value">""" + str(curr_y.get("inv",0)) + """</div><div class="kpi-label">Involuntary &mdash; """ + str(CY) + """</div><div class="kpi-sub">Terminations YTD</div></div>
    <div class="kpi amber"><div class="kpi-value">""" + str(curr_y.get("turnover",0)) + """%</div><div class="kpi-label">Turnover Rate """ + str(CY) + """</div><div class="kpi-sub">Exits / Avg HC</div></div>
    <div class="kpi purple"><div class="kpi-value">""" + str(avg_tenure) + """</div><div class="kpi-label">Avg. Tenure</div><div class="kpi-sub">Years (active)</div></div>
    <div class="kpi teal"><div class="kpi-value">""" + str(len(terminated)) + """</div><div class="kpi-label">All-Time Exits</div><div class="kpi-sub">Historical total</div></div>
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
  <div class="section-label">Exit Reasons (2023&ndash;""" + str(CY) + """)</div>
  <div class="grid-2">
    <div class="card"><div class="card-title"><span class="dot dot-orange"></span>Voluntary Exit Reasons</div><div style="height:240px"><canvas id="cVR"></canvas></div></div>
    <div class="card"><div class="card-title"><span class="dot dot-red"></span>Involuntary Exit Reasons</div><div style="height:240px"><canvas id="cIR"></canvas></div></div>
  </div>
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
const C={blue:'#2563EB',green:'#16A34A',red:'#DC2626',orange:'#EA580C',purple:'#7C3AED',teal:'#0D9488',amber:'#D97706',rose:'#E11D48',indigo:'#4F46E5',pink:'#DB2777'};
const PAL=Object.values(C);
Chart.defaults.font.family="'Plus Jakarta Sans','Segoe UI',system-ui,sans-serif";
Chart.defaults.font.size=12;Chart.defaults.color='#6B7280';Chart.defaults.borderColor='#E8ECF0';
Chart.defaults.plugins.legend.labels.usePointStyle=true;Chart.defaults.plugins.legend.labels.padding=16;
const YRS=""" + YEARS_JS + """;
new Chart('cHC',{type:'line',data:{labels:YRS,datasets:[{label:'Headcount',data:""" + HC_JS + """,borderColor:C.blue,backgroundColor:'rgba(37,99,235,.1)',fill:true,tension:.4,borderWidth:2.5,pointRadius:4,pointBackgroundColor:C.blue,pointBorderColor:'#fff',pointBorderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:'#F3F4F6'}}}}});
new Chart('cHT',{type:'bar',data:{labels:YRS,datasets:[{label:'New Hires',data:""" + HIRES_JS + """,backgroundColor:C.green,borderRadius:4},{label:'Exits',data:""" + TERMS_JS + """,backgroundColor:C.red,borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#F3F4F6'}}}}});
new Chart('cTO',{type:'line',data:{labels:YRS,datasets:[{label:'Turnover %',data:""" + TURNOVER_JS + """,borderColor:C.amber,backgroundColor:'rgba(217,119,6,.1)',fill:true,tension:.4,borderWidth:2.5,pointRadius:4,pointBackgroundColor:C.amber,pointBorderColor:'#fff',pointBorderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:'#F3F4F6'},ticks:{callback:v=>v+'%'}}}}});
new Chart('cVI',{type:'bar',data:{labels:YRS,datasets:[{label:'Voluntary',data:""" + VOL_JS + """,backgroundColor:C.orange,borderRadius:4},{label:'Involuntary',data:""" + INV_JS + """,backgroundColor:C.red,borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#F3F4F6'}}}}});
new Chart('cMon',{type:'bar',data:{labels:""" + ML_JS + """,datasets:[{label:'New Hires',data:""" + MH_JS + """,backgroundColor:'rgba(22,163,74,.75)',borderRadius:3},{label:'Exits',data:""" + MT_JS + """,backgroundColor:'rgba(220,38,38,.75)',borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#F3F4F6'}}}}});
new Chart('cDept',{type:'bar',data:{labels:""" + DEPT_L_JS + """,datasets:[{data:""" + DEPT_V_JS + """,backgroundColor:PAL,borderRadius:4,barThickness:18}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:'#F3F4F6'}},y:{grid:{display:false}}}}});
new Chart('cLoc',{type:'doughnut',data:{labels:""" + LOC_L_JS + """,datasets:[{data:""" + LOC_V_JS + """,backgroundColor:PAL,borderWidth:2,borderColor:'#fff',hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom',labels:{font:{size:11}}}}}});
new Chart('cGen',{type:'doughnut',data:{labels:""" + GEN_L_JS + """,datasets:[{data:""" + GEN_V_JS + """,backgroundColor:[C.blue,C.pink,C.teal],borderWidth:2,borderColor:'#fff',hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom'}}}});
new Chart('cTen',{type:'bar',data:{labels:['< 1 yr','1-2 yrs','2-4 yrs','4+ yrs'],datasets:[{data:""" + TEN_V_JS + """,backgroundColor:[C.red,C.orange,C.amber,C.green],borderRadius:6,barThickness:36}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#F3F4F6'}}}}});
new Chart('cDiv',{type:'doughnut',data:{labels:""" + DIV_L_JS + """,datasets:[{data:""" + DIV_V_JS + """,backgroundColor:PAL,borderWidth:2,borderColor:'#fff',hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom',labels:{font:{size:11}}}}}});
new Chart('cVR',{type:'bar',data:{labels:""" + VR_L_JS + """,datasets:[{data:""" + VR_V_JS + """,backgroundColor:'rgba(234,88,12,.8)',borderRadius:4,barThickness:18}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:'#F3F4F6'}},y:{grid:{display:false}}}}});
new Chart('cIR',{type:'bar',data:{labels:""" + IR_L_JS + """,datasets:[{data:""" + IR_V_JS + """,backgroundColor:'rgba(220,38,38,.8)',borderRadius:4,barThickness:18}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:'#F3F4F6'}},y:{grid:{display:false}}}}});
</script>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"Done — index.html generated ({TODAY_STR})")
