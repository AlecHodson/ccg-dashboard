import requests, json, base64, os, pickle, re
from datetime import datetime
from PIL import Image
import io

# ── Config ──────────────────────────────────────────────────────────────────
FAMLY_TOKEN = os.environ["FAMLY_TOKEN"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = "AlecHodson/ccg-dashboard"

endpoint = "https://famlyapi.famly.co/v1/graphql"
famly_headers = {"X-Famly-Accesstoken": FAMLY_TOKEN, "Content-Type": "application/json"}
gh_headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

pav_sites = [
    "0fdd55f4-22d4-4b91-8c48-c59e52c145b0","7c7fe58a-c4fc-4da1-9bc5-c1f4ac362181",
    "7aa31205-16c2-44dd-a9c7-9eef734e3fae","d89c775f-3d95-46ba-a2b7-5f78e1fe7d63",
    "d9df733b-3236-4b26-b98e-1df86103f9fb","6ea210bf-8ff3-4696-a835-48c6ff62d45c",
    "b5e4e0c0-2e66-42a3-a9bb-ee3cc47ae322","1d0adba0-d011-4673-bf78-fd4bd27ab60a",
    "d4b8f6a1-14e2-4522-9143-5c9de302ea38",
]
leanne_sites = [
    "22bcd90e-dc96-4ca8-a00f-e5030a6b7543","eaf4f874-a515-491b-9b0d-2258a7caee0c",
    "41ba7194-06ae-439d-963c-7f1f6742b4d7","b743e309-9fd7-4974-936b-d098845dc921",
    "81c8015b-f36a-4bb1-9822-9bad9f573076","d9e82f06-63d0-4892-9d99-4e9bcbc81916",
    "8c25833b-bc4a-4139-a763-c4a317fd2bb8","b5fe3245-5735-4fb3-91fa-4d0acbe61589",
]
site_names = {
    "0fdd55f4-22d4-4b91-8c48-c59e52c145b0":"Abacus","7c7fe58a-c4fc-4da1-9bc5-c1f4ac362181":"Cedars",
    "7aa31205-16c2-44dd-a9c7-9eef734e3fae":"Boot Farm","d89c775f-3d95-46ba-a2b7-5f78e1fe7d63":"Lower Earley",
    "d9df733b-3236-4b26-b98e-1df86103f9fb":"Our Den","6ea210bf-8ff3-4696-a835-48c6ff62d45c":"Bees Knees",
    "b5e4e0c0-2e66-42a3-a9bb-ee3cc47ae322":"Northumberland","1d0adba0-d011-4673-bf78-fd4bd27ab60a":"Saltway",
    "d4b8f6a1-14e2-4522-9143-5c9de302ea38":"Smart Tots","22bcd90e-dc96-4ca8-a00f-e5030a6b7543":"Bramley Wood",
    "eaf4f874-a515-491b-9b0d-2258a7caee0c":"Finchampstead","41ba7194-06ae-439d-963c-7f1f6742b4d7":"Happitots",
    "b743e309-9fd7-4974-936b-d098845dc921":"Hazebrouck","81c8015b-f36a-4bb1-9822-9bad9f573076":"Kingsclere",
    "d9e82f06-63d0-4892-9d99-4e9bcbc81916":"Merrydale","8c25833b-bc4a-4139-a763-c4a317fd2bb8":"Stepping Stones",
    "b5fe3245-5735-4fb3-91fa-4d0acbe61589":"Woosehill",
}
all_sites = pav_sites + leanne_sites
site_ids_str = json.dumps(all_sites)
cutoff_june   = datetime(2026, 6, 1)
cutoff_target = datetime(2026, 8, 18)

# ── Fetch Famly data ─────────────────────────────────────────────────────────
print("Fetching Famly data...")
all_results = []
cursor = None
for _ in range(30):
    cursor_arg = ', cursor: "' + cursor + '"' if cursor else ""
    query = "{ inquiries { listBySiteIdsPaginated(siteIds: " + site_ids_str + ", pageSize: 500" + cursor_arg + ") { results { id siteId status createdAt } next } } }"
    resp = requests.post(endpoint, json={"query": query}, headers=famly_headers)
    page = resp.json()["data"]["inquiries"]["listBySiteIdsPaginated"]
    results = page["results"]
    all_results.extend(results)
    cursor = page.get("next")
    if results:
        oldest = min(datetime.fromisoformat(r["createdAt"].replace("Z","")) for r in results)
        if oldest < cutoff_june and not cursor:
            break
    if not cursor:
        break
print(f"Fetched {len(all_results)} records")

# ── Aggregate stats ──────────────────────────────────────────────────────────
june_stats    = {sid: {"NEW":0,"CONTACTED":0,"VIEWED":0,"WAITING_LIST":0,"CONFIRMED":0,"ENROLLED":0,"LOST":0,"total":0} for sid in all_sites}
june_enrolled = {sid: 0 for sid in all_sites}
target_enrolled = {sid: 0 for sid in all_sites}

for r in all_results:
    sid = r["siteId"]
    if sid not in june_stats: continue
    dt = datetime.fromisoformat(r["createdAt"].replace("Z",""))
    status = r["status"]
    if dt >= cutoff_june:
        june_stats[sid][status] = june_stats[sid].get(status, 0) + 1
        june_stats[sid]["total"] += 1
        if status == "ENROLLED":
            june_enrolled[sid] += 1
    if dt >= cutoff_target and status == "ENROLLED":
        target_enrolled[sid] += 1

# ── Load previous baseline from GitHub ──────────────────────────────────────
prev_enrolled = {}
try:
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/baseline.json", headers=gh_headers)
    if r.status_code == 200:
        prev_enrolled = json.loads(base64.b64decode(r.json()["content"]).decode())
        print(f"Baseline loaded: {len(prev_enrolled)} nurseries")
except Exception as e:
    print(f"No baseline found: {e}")

new_registrations = {sid: max(0, june_enrolled[sid] - prev_enrolled.get(sid, 0)) for sid in all_sites if june_enrolled[sid] > prev_enrolled.get(sid, 0)}
print(f"New registrations: {new_registrations}")

# ── Photos (embedded as base64) ──────────────────────────────────────────────
PAV_URL = "https://aiosproduction.blob.core.windows.net/ai-os-production-storage/command_team/5c0c39e3-1600-4a3e-85fa-58218647d4d6/83cc0d9c-16ec-4f24-88cd-5a42cea7b0d0/files/ab4c980a-1da7-4d96-b827-721ea50d0155/aa65a2fb-d15f-4a5c-8126-9cd4b24c90b8.jpg"
LEANNE_URL = "https://aiosproduction.blob.core.windows.net/ai-os-production-storage/command_team/5c0c39e3-1600-4a3e-85fa-58218647d4d6/83cc0d9c-16ec-4f24-88cd-5a42cea7b0d0/files/0fa387cc-60c3-456f-95a3-6a1654a7a78c/abd4cb8d-5658-4b3f-b93b-5081a014e0f0.jpg"

def compress(url, size, quality=65):
    r = requests.get(url)
    img = Image.open(io.BytesIO(r.content)).convert("RGB").resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")

pav_face=compress(PAV_URL,28); pav_head=compress(PAV_URL,110)
leanne_face=compress(LEANNE_URL,28); leanne_head=compress(LEANNE_URL,110)

# ── Helpers ──────────────────────────────────────────────────────────────────
def area_totals(sids):
    total=enrolled=confirmed=wl=lost=active=0
    for sid in sids:
        s=june_stats[sid]
        total+=s["total"]; enrolled+=s["ENROLLED"]; confirmed+=s["CONFIRMED"]
        wl+=s["WAITING_LIST"]; lost+=s["LOST"]
        active+=s["NEW"]+s["CONTACTED"]+s["VIEWED"]
    conv=round(enrolled/total*100,1) if total>0 else 0
    return {"total":total,"enrolled":enrolled,"pipeline":confirmed+wl,"active":active,"conv":conv}

def nursery_rows(sids):
    rows=[]
    for sid in sids:
        s=june_stats[sid]; total=s["total"]; enrolled=s["ENROLLED"]
        pipeline=s["CONFIRMED"]+s["WAITING_LIST"]
        conv=round(enrolled/total*100,1) if total>0 else 0
        rows.append({"sid":sid,"name":site_names[sid],"total":total,"enrolled":enrolled,
                     "pipeline":pipeline,"lost":s["LOST"],"conv":conv,"new":new_registrations.get(sid,0)})
    return sorted(rows, key=lambda x: -x["conv"])

def cc(c):
    return "#22c55e" if c>=30 else ("#f59e0b" if c>=15 else ("#f97316" if c>0 else "#94a3b8"))

def face_bar(enrolled, face_b64, border):
    show=min(enrolled,18); overflow=enrolled-show
    imgs="".join('<img src="data:image/jpeg;base64,'+face_b64+'" style="width:26px;height:26px;border-radius:50%;object-fit:cover;border:2px solid '+border+';margin-right:2px;vertical-align:middle;">' for _ in range(show))
    if overflow>0: imgs+='<span style="display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;background:rgba(0,0,0,.15);border:2px solid '+border+';font-size:9px;font-weight:800;color:#fff;vertical-align:middle;">+'+str(overflow)+'</span>'
    if enrolled==0: imgs='<span style="font-size:11px;color:#94a3b8;font-style:italic;">No registrations yet</span>'
    return '<div style="line-height:1;padding:4px 0;">'+imgs+'</div>'

def nrow(r, fb, border):
    color=cc(r["conv"])
    new_badge=""
    if r["new"]>0:
        n_label="+"+str(r["new"])+" NEW!" if r["new"]>1 else "NEW!"
        new_badge=('<span style="display:inline-block;background:#ff3b3b;color:#fff;'+
                   'font-size:9px;font-weight:900;padding:2px 6px;border-radius:20px;'+
                   'margin-left:5px;letter-spacing:0.5px;vertical-align:middle;'+
                   'animation:flash 1s infinite;box-shadow:0 0 8px rgba(255,59,59,0.6);">'+n_label+'</span>')
    row_style=' style="background:linear-gradient(90deg,rgba(255,59,59,0.06),transparent);"' if r["new"]>0 else ""
    return ('<tr'+row_style+'>'+
        '<td style="padding:8px 6px 8px 0;font-size:12px;font-weight:700;color:#334155;white-space:nowrap;">'+r["name"]+new_badge+'</td>'+
        '<td style="padding:8px 4px;"><span style="background:'+color+';color:#fff;font-size:10px;font-weight:800;padding:2px 7px;border-radius:5px;">'+str(r["conv"])+'%</span></td>'+
        '<td style="padding:8px 4px;">'+face_bar(r["enrolled"],fb,border)+'</td>'+
        '<td style="padding:8px 4px;font-size:18px;font-weight:900;color:'+color+';text-align:right;">'+str(r["enrolled"])+'</td>'+
        '<td style="padding:8px 0 8px 4px;font-size:10px;color:#94a3b8;white-space:nowrap;">'+str(r["pipeline"])+' pipe / '+str(r["lost"])+' lost</td>'+
        '</tr>')

def ring(conv, color, size=80):
    c=213.6; off=round(c-(c*conv/100),1)
    return ('<svg width="'+str(size)+'" height="'+str(size)+'" viewBox="0 0 80 80" style="transform:rotate(-90deg);">'+
        '<circle cx="40" cy="40" r="34" fill="none" stroke="rgba(0,0,0,.08)" stroke-width="8"/>'+
        '<circle cx="40" cy="40" r="34" fill="none" stroke="'+color+'" stroke-width="8" stroke-dasharray="'+str(c)+'" stroke-dashoffset="'+str(off)+'" stroke-linecap="round"/>'+
        '</svg>')

def tgt_bar(actual, target, pct, remaining, grad, label_color, status_text):
    return ('<div class="tgt-hd"><span class="tgt-lbl">Target: 18 Aug - 31 Dec 2026</span>'+
        '<span class="tgt-frac">'+str(actual)+' <span style="color:#94a3b8;font-size:15px;">/ '+str(target)+' FTE</span></span></div>'+
        '<div class="tgt-bar"><div class="tgt-fill" style="width:'+str(min(pct,100))+'%;background:'+grad+';"></div></div>'+
        '<div class="tgt-ft"><span class="tgt-st" style="color:'+label_color+';">'+status_text+'</span>'+
        '<span class="tgt-rem"><strong>'+str(remaining)+'</strong> to go / <strong>'+str(pct)+'%</strong> done</span></div>')

# ── Compute everything ───────────────────────────────────────────────────────
pav_totals=area_totals(pav_sites); leanne_totals=area_totals(leanne_sites)
pav_rows=nursery_rows(pav_sites); leanne_rows=nursery_rows(leanne_sites)
bw_actual=sum(target_enrolled[s] for s in pav_sites)
gw_actual=sum(target_enrolled[s] for s in leanne_sites)
bw_target=37; gw_target=38
bw_remaining=max(0,bw_target-bw_actual); gw_remaining=max(0,gw_target-gw_actual)
bw_pct=round(bw_actual/bw_target*100,1); gw_pct=round(gw_actual/gw_target*100,1)
group_total=pav_totals["total"]+leanne_totals["total"]
group_enrolled=pav_totals["enrolled"]+leanne_totals["enrolled"]
group_conv=round(group_enrolled/group_total*100,1) if group_total>0 else 0
group_pipeline=pav_totals["pipeline"]+leanne_totals["pipeline"]
now_str=datetime.now().strftime("%d %B %Y at %H:%M")
pr=ring(pav_totals["conv"],"#7c3aed"); lr=ring(leanne_totals["conv"],"#0891b2"); gr=ring(group_conv,"#ea580c",70)
ph="".join(nrow(r,pav_face,"#a78bfa") for r in pav_rows)
lh="".join(nrow(r,leanne_face,"#22d3ee") for r in leanne_rows)
bw_status="Period opens today!" if bw_actual==0 else ("On track!" if bw_pct>=80 else "Getting there!")
gw_status=str(gw_actual)+" registered!" if 0<gw_actual<5 else ("On track!" if gw_pct>=80 else "Getting there!" if gw_actual>0 else "Period opens today!")
total_new=sum(new_registrations.values())
new_banner=""
if total_new>0:
    nursery_names=", ".join(site_names[sid] for sid in new_registrations)
    new_banner=('<div style="background:linear-gradient(90deg,#ff3b3b,#ff6b35);color:#fff;'+
                'text-align:center;padding:10px 20px;font-size:13px;font-weight:800;'+
                'letter-spacing:0.5px;animation:flash 1.5s infinite;">'+
                'NEW REGISTRATIONS TODAY: +'+str(total_new)+' at '+nursery_names+'!'+
                '</div>')

# ── Build HTML ───────────────────────────────────────────────────────────────
css="""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:linear-gradient(135deg,#fef9c3 0%,#fce7f3 40%,#dbeafe 100%);color:#1e293b;min-height:100vh}
@keyframes flash{0%,100%{opacity:1}50%{opacity:0.6}}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(74,222,128,.5)}50%{box-shadow:0 0 0 7px rgba(74,222,128,0)}}
.wrap{max-width:1400px;margin:0 auto;padding:20px}
.header{text-align:center;padding:36px 32px;background:linear-gradient(135deg,#7c3aed,#0891b2);border-radius:24px;box-shadow:0 16px 50px rgba(124,58,237,.3);margin-bottom:24px}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:rgba(255,255,255,.7);margin-bottom:8px}
h1{font-size:36px;font-weight:900;color:#fff;line-height:1.1;margin-bottom:8px}
.date-badge{display:inline-block;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.3);border-radius:20px;padding:5px 16px;font-size:13px;font-weight:700;color:#fff;margin:8px 0}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
.kpi{background:#fff;border-radius:18px;padding:18px 14px;text-align:center;box-shadow:0 4px 16px rgba(0,0,0,.07);border:2px solid transparent}
.kpi-lbl{font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#94a3b8;margin-bottom:6px}
.kpi-val{font-size:42px;font-weight:900;line-height:1}
.kpi-sub{font-size:10px;color:#94a3b8;margin-top:4px}
.vs{display:flex;align-items:center;justify-content:center;gap:24px;padding:16px 32px;background:linear-gradient(135deg,#7c3aed,#a855f7 45%,#0891b2);border-radius:18px;box-shadow:0 8px 28px rgba(124,58,237,.25);margin-bottom:20px}
.vs-name{font-size:20px;font-weight:900;color:#fff}
.vs-score{font-size:38px;font-weight:900;color:#fff}
.vs-lbl{font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,.6);margin-top:2px}
.vs-mid{font-size:30px;font-weight:900;color:#fde68a}
.legend{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin-bottom:18px;align-items:center}
.leg{display:flex;align-items:center;gap:5px;font-size:11px;color:#64748b;font-weight:600}
.leg-dot{width:10px;height:10px;border-radius:3px;display:inline-block}
.new-leg{display:inline-block;background:#ff3b3b;color:#fff;font-size:9px;font-weight:900;padding:2px 7px;border-radius:20px;letter-spacing:0.5px;animation:flash 1s infinite}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
.panel{background:#fff;border-radius:22px;overflow:hidden;box-shadow:0 6px 32px rgba(0,0,0,.09)}
.pav-panel{border-top:6px solid #7c3aed}.lea-panel{border-top:6px solid #0891b2}
.panel-head{padding:22px;display:flex;align-items:center;gap:16px}
.pav-head{background:linear-gradient(135deg,#f5f3ff,#ede9fe)}.lea-head{background:linear-gradient(135deg,#ecfeff,#cffafe)}
.av-wrap{position:relative;flex-shrink:0}
.av-img{width:96px;height:96px;border-radius:50%;object-fit:cover;object-position:center top;border:4px solid #fff;box-shadow:0 4px 16px rgba(0,0,0,.18);display:block}
.av-badge{position:absolute;bottom:-2px;right:-8px;border-radius:12px;padding:3px 9px;border:3px solid #fff;text-align:center;min-width:50px}
.av-num{display:block;font-size:17px;font-weight:900;color:#fff;line-height:1}
.av-lbl{display:block;font-size:7px;font-weight:700;color:rgba(255,255,255,.8);letter-spacing:1px;text-transform:uppercase}
.mgr-name{font-size:21px;font-weight:900;color:#0f172a;margin-bottom:2px}
.mgr-lbl{font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#64748b;margin-bottom:10px}
.mini-kpis{display:flex;gap:8px;flex-wrap:wrap}
.mk{border-radius:10px;padding:7px 12px;text-align:center}
.mk-v{font-size:20px;font-weight:900;line-height:1}.mk-l{font-size:8px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#94a3b8;margin-top:1px}
.ring-wrap{flex-shrink:0;display:flex;flex-direction:column;align-items:center}
.ring-box{width:80px;height:80px;position:relative}
.ring-lbl{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:13px;font-weight:900;color:#0f172a}
.ring-sub{font-size:8px;color:#94a3b8;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-top:4px;text-align:center}
.tgt{margin:0 22px 18px;border-radius:14px;padding:14px 16px}
.pav-tgt{background:linear-gradient(135deg,#f5f3ff,#ede9fe);border:2px solid #c4b5fd}
.lea-tgt{background:linear-gradient(135deg,#ecfeff,#cffafe);border:2px solid #67e8f9}
.tgt-hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.tgt-lbl{font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#64748b}
.tgt-frac{font-size:22px;font-weight:900;color:#0f172a}
.tgt-bar{background:rgba(0,0,0,.08);border-radius:6px;height:12px;overflow:hidden;margin-bottom:7px}
.tgt-fill{height:100%;border-radius:6px}
.tgt-ft{display:flex;justify-content:space-between}
.tgt-st{font-size:11px;font-weight:800}.tgt-rem{font-size:11px;color:#64748b}
.sec-hd{font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#94a3b8;padding:10px 22px 6px;border-top:2px solid #f1f5f9;display:flex;justify-content:space-between}
.tbl-wrap{padding:0 22px 20px}
table{width:100%;border-collapse:collapse}
.footer{text-align:center;padding:16px;font-size:11px;color:#94a3b8}
@media(max-width:900px){.kpis{grid-template-columns:repeat(3,1fr)}.grid{grid-template-columns:1fr}}
@media(max-width:580px){.kpis{grid-template-columns:repeat(2,1fr)}}
"""

html_parts=[]
html_parts.append("<!DOCTYPE html>")
html_parts.append('<html lang="en"><head>')
html_parts.append('<meta charset="UTF-8">')
html_parts.append('<meta http-equiv="Content-Type" content="text/html; charset=utf-8">')
html_parts.append('<meta name="viewport" content="width=device-width,initial-scale=1.0">')
html_parts.append('<title>CCG Conversion Challenge Dashboard</title>')
html_parts.append("<style>"+css+"</style>")
html_parts.append("</head><body>")
if new_banner: html_parts.append(new_banner)
html_parts.append('<div class="wrap">')
html_parts.append('<div class="header"><div class="eyebrow">Complete Childcare Group - 17 Nurseries</div><h1>Enquiry to Registration Conversion Challenge</h1><div class="date-badge">Cumulative from 1 June 2026</div><div style="font-size:12px;color:rgba(255,255,255,.65);margin-top:6px;">Updated '+now_str+'</div></div>')
html_parts.append('<div class="kpis">'+
    '<div class="kpi" style="border-color:#e0e7ff;"><div class="kpi-lbl">Total Enquiries</div><div class="kpi-val" style="color:#7c3aed;">'+str(group_total)+'</div><div class="kpi-sub">Since 1 Jun 2026</div></div>'+
    '<div class="kpi" style="border-color:#d1fae5;"><div class="kpi-lbl">Registered</div><div class="kpi-val" style="color:#059669;">'+str(group_enrolled)+'</div><div class="kpi-sub">Enrolled children</div></div>'+
    '<div class="kpi" style="border-color:#fed7aa;"><div class="kpi-lbl">Group Conversion</div><div style="display:flex;justify-content:center;margin:2px 0;"><div style="width:70px;height:70px;position:relative;">'+gr+'<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:14px;font-weight:900;color:#ea580c;">'+str(group_conv)+'%</div></div></div><div class="kpi-sub">Enquiry to Registration</div></div>'+
    '<div class="kpi" style="border-color:#e9d5ff;"><div class="kpi-lbl">In Pipeline</div><div class="kpi-val" style="color:#9333ea;">'+str(group_pipeline)+'</div><div class="kpi-sub">Confirmed + Waiting</div></div>'+
    '<div class="kpi" style="border-color:#cffafe;"><div class="kpi-lbl">Still Active</div><div class="kpi-val" style="color:#0891b2;">'+str(pav_totals["active"]+leanne_totals["active"])+'</div><div class="kpi-sub">In progress</div></div>'+
    '</div>')
html_parts.append('<div class="vs"><div style="text-align:right;"><div class="vs-name">BlueWater</div><div class="vs-score">'+str(pav_totals["enrolled"])+'</div><div class="vs-lbl">Registrations</div></div><div class="vs-mid">VS</div><div style="text-align:left;"><div class="vs-name">Greenwood</div><div class="vs-score">'+str(leanne_totals["enrolled"])+'</div><div class="vs-lbl">Registrations</div></div></div>')
html_parts.append('<div class="legend"><div class="leg"><span class="leg-dot" style="background:#22c55e;"></span>Strong 30%+</div><div class="leg"><span class="leg-dot" style="background:#f59e0b;"></span>Good 15-29%</div><div class="leg"><span class="leg-dot" style="background:#f97316;"></span>Building under 15%</div><div class="leg"><span class="leg-dot" style="background:#94a3b8;"></span>Not started</div><div class="leg"><span class="new-leg">NEW!</span> New since last update</div></div>')
html_parts.append('<div class="grid">')
html_parts.append('<div class="panel pav-panel"><div class="panel-head pav-head">'+
    '<div class="av-wrap"><img class="av-img" src="data:image/jpeg;base64,'+pav_head+'" alt="Pav Bilkhu"><div class="av-badge" style="background:#7c3aed;"><span class="av-num">'+str(pav_totals["enrolled"])+'</span><span class="av-lbl">Registered</span></div></div>'+
    '<div style="flex:1;min-width:0;"><div class="mgr-name">Pav Bilkhu</div><div class="mgr-lbl">BlueWater - 9 Nurseries</div>'+
    '<div class="mini-kpis"><div class="mk" style="background:#f5f3ff;"><div class="mk-v" style="color:#7c3aed;">'+str(pav_totals["total"])+'</div><div class="mk-l">Enquiries</div></div>'+
    '<div class="mk" style="background:#f0fdf4;"><div class="mk-v" style="color:#059669;">'+str(pav_totals["enrolled"])+'</div><div class="mk-l">Registered</div></div>'+
    '<div class="mk" style="background:#faf5ff;"><div class="mk-v" style="color:#9333ea;">'+str(pav_totals["pipeline"])+'</div><div class="mk-l">Pipeline</div></div>'+
    '<div class="mk" style="background:#ecfeff;"><div class="mk-v" style="color:#0891b2;">'+str(pav_totals["active"])+'</div><div class="mk-l">Active</div></div></div></div>'+
    '<div class="ring-wrap"><div class="ring-box">'+pr+'<div class="ring-lbl">'+str(pav_totals["conv"])+'%</div></div><div class="ring-sub">Conversion</div></div></div>'+
    '<div class="tgt pav-tgt">'+tgt_bar(bw_actual,bw_target,bw_pct,bw_remaining,"linear-gradient(90deg,#7c3aed,#a855f7)","#7c3aed",bw_status)+'</div>'+
    '<div class="sec-hd"><span>Nursery Breakdown - each face = 1 registration</span><span>Conv% / Pipeline / Lost</span></div>'+
    '<div class="tbl-wrap"><table>'+ph+'</table></div></div>')
html_parts.append('<div class="panel lea-panel"><div class="panel-head lea-head">'+
    '<div class="av-wrap"><img class="av-img" src="data:image/jpeg;base64,'+leanne_head+'" alt="Leanne Maynard"><div class="av-badge" style="background:#0891b2;"><span class="av-num">'+str(leanne_totals["enrolled"])+'</span><span class="av-lbl">Registered</span></div></div>'+
    '<div style="flex:1;min-width:0;"><div class="mgr-name">Leanne Maynard</div><div class="mgr-lbl">Greenwood - 8 Nurseries</div>'+
    '<div class="mini-kpis"><div class="mk" style="background:#ecfeff;"><div class="mk-v" style="color:#0891b2;">'+str(leanne_totals["total"])+'</div><div class="mk-l">Enquiries</div></div>'+
    '<div class="mk" style="background:#f0fdf4;"><div class="mk-v" style="color:#059669;">'+str(leanne_totals["enrolled"])+'</div><div class="mk-l">Registered</div></div>'+
    '<div class="mk" style="background:#faf5ff;"><div class="mk-v" style="color:#9333ea;">'+str(leanne_totals["pipeline"])+'</div><div class="mk-l">Pipeline</div></div>'+
    '<div class="mk" style="background:#ecfeff;"><div class="mk-v" style="color:#0891b2;">'+str(leanne_totals["active"])+'</div><div class="mk-l">Active</div></div></div></div>'+
    '<div class="ring-wrap"><div class="ring-box">'+lr+'<div class="ring-lbl">'+str(leanne_totals["conv"])+'%</div></div><div class="ring-sub">Conversion</div></div></div>'+
    '<div class="tgt lea-tgt">'+tgt_bar(gw_actual,gw_target,gw_pct,gw_remaining,"linear-gradient(90deg,#0891b2,#22d3ee)","#0891b2",gw_status)+'</div>'+
    '<div class="sec-hd"><span>Nursery Breakdown - each face = 1 registration</span><span>Conv% / Pipeline / Lost</span></div>'+
    '<div class="tbl-wrap"><table>'+lh+'</table></div></div>')
html_parts.append('</div>')
html_parts.append('<div class="footer">Complete Childcare Group - Famly data from 1 June 2026 - Target: 18 Aug to 31 Dec 2026 - NEW badge shows registrations gained since last daily update</div>')
html_parts.append('</div></body></html>')

html = "\n".join(html_parts)
print(f"HTML built: {len(html.encode())//1024} KB")

# ── Push index.html to GitHub ────────────────────────────────────────────────
r = requests.get(f"https://api.github.com/repos/{REPO}/contents/index.html", headers=gh_headers)
sha = r.json().get("sha","")
content_b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
resp = requests.put(f"https://api.github.com/repos/{REPO}/contents/index.html", headers=gh_headers, json={
    "message": f"Auto-update: {now_str}",
    "content": content_b64,
    "sha": sha
})
print(f"GitHub push: {resp.status_code}")

# ── Save baseline.json to GitHub ─────────────────────────────────────────────
baseline_content = base64.b64encode(json.dumps(june_enrolled).encode()).decode("ascii")
r2 = requests.get(f"https://api.github.com/repos/{REPO}/contents/baseline.json", headers=gh_headers)
sha2 = r2.json().get("sha","") if r2.status_code==200 else ""
resp2 = requests.put(f"https://api.github.com/repos/{REPO}/contents/baseline.json", headers=gh_headers, json={
    "message": f"Baseline update: {now_str}",
    "content": baseline_content,
    "sha": sha2
})
print(f"Baseline push: {resp2.status_code}")
print("Done!")
