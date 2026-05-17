"""
Garmin Dashboard Generator
Reads from garmin_cache.json (API) + old export files, generates full interactive HTML.
"""
import json
import os
import glob
from datetime import datetime, date, timedelta
from collections import defaultdict

OLD_BASE    = os.environ.get("GARMIN_OLD_BASE", "")
OLD_SLEEP   = os.path.join(OLD_BASE, "DI-Connect-Wellness")  if OLD_BASE else ""
OLD_STEPS   = os.path.join(OLD_BASE, "DI-Connect-Aggregator") if OLD_BASE else ""
# 優先讀 GARMIN_DATA_FILE（新版），回退到 GARMIN_CACHE_FILE（舊版）
CACHE_FILE  = os.environ.get("GARMIN_DATA_FILE",
              os.environ.get("GARMIN_CACHE_FILE", r"C:\Users\USER\Desktop\garmin_data.json"))
OUTPUT      = os.environ.get("GARMIN_OUTPUT",     r"C:\Users\USER\Desktop\garmin_dashboard.html")

# ── 舊匯出檔 ──────────────────────────────────────────────
steps_old, sleep_old, hr_old = {}, {}, {}

for f in sorted(glob.glob(os.path.join(OLD_STEPS, "UDSFile_*.json")) if OLD_STEPS else []):
    try:
        with open(f, encoding="utf-8") as fp:
            for r in json.load(fp):
                d = r.get("calendarDate", "")
                s = r.get("totalSteps")
                if d and s is not None:
                    steps_old[d] = int(s)
                hr = r.get("restingHeartRate")
                if d and hr:
                    hr_old.setdefault(d, {})["hr"] = hr
                ac = r.get("activeKilocalories")
                tc = r.get("totalKilocalories")
                if d and (ac or tc):
                    hr_old.setdefault(d, {})
                    if ac: hr_old[d]["active_cal"] = ac
                    if tc: hr_old[d]["total_cal"]  = tc
    except Exception:
        pass

for f in sorted(glob.glob(os.path.join(OLD_SLEEP, "*sleepData*.json")) if OLD_SLEEP else []):
    try:
        with open(f, encoding="utf-8") as fp:
            for r in json.load(fp):
                d = r.get("calendarDate", "")
                sc = r.get("sleepScores", {})
                score = sc.get("overallScore") if sc else None
                if d and score is not None:
                    sleep_old[d] = {
                        "score": score,
                        "deep":  round(r.get("deepSleepSeconds", 0) / 3600, 2),
                        "light": round(r.get("lightSleepSeconds", 0) / 3600, 2),
                        "rem":   round(r.get("remSleepSeconds", 0) / 3600, 2),
                        "awake": round(r.get("awakeSleepSeconds", 0) / 3600, 2),
                        "start": r.get("sleepStartTimestampGMT"),
                        "end":   r.get("sleepEndTimestampGMT"),
                    }
    except Exception:
        pass

# ── 新快取 (優先覆蓋) ─────────────────────────────────────
steps_new, sleep_new, hr_new = {}, {}, {}

fetched_at = ""
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, encoding="utf-8") as fp:
        cache = json.load(fp)

    fetched_at = cache.get("fetched_at", "")

    for r in cache.get("steps", []):
        d, s = r.get("calendarDate", ""), r.get("totalSteps")
        if d and s:  # 只接受 > 0 的值，不用 0 覆蓋舊資料
            steps_new[d] = int(s)

    for r in cache.get("sleep", []):
        d     = r.get("calendarDate", "")
        score = r.get("overallScore")
        if d and score is not None:
            sleep_new[d] = {
                "score": score,
                "deep":  round(r.get("deepSleepSeconds", 0) / 3600, 2),
                "light": round(r.get("lightSleepSeconds", 0) / 3600, 2),
                "rem":   round(r.get("remSleepSeconds", 0) / 3600, 2),
                "awake": round(r.get("awakeSleepSeconds", 0) / 3600, 2),
                "start": r.get("sleepStartTimestampGMT"),
                "end":   r.get("sleepEndTimestampGMT"),
            }

    for d, v in cache.get("hr_cal", {}).items():
        hr_new[d] = {
            "hr":         v.get("restingHeartRate"),
            "active_cal": v.get("activeKilocalories"),
            "total_cal":  v.get("totalKilocalories"),
        }

    # 每小時步數（已由 garmin_fetch.py 聚合，直接讀取）
    steps_hourly_new = cache.get("steps_hourly", {})

# ── 合併（新快取優先）─────────────────────────────────────
steps_all    = {**steps_old, **steps_new}
sleep_all    = {**sleep_old, **sleep_new}
hr_all       = {**hr_old,    **hr_new}
steps_hourly = steps_hourly_new if 'steps_hourly_new' in dir() else {}

all_dates = sorted(set(list(steps_all.keys()) + list(sleep_all.keys())))

daily = []
for d in all_dates:
    sl = sleep_all.get(d, {})
    hc = hr_all.get(d, {})
    total_h = round(sl.get("deep", 0) + sl.get("light", 0) + sl.get("rem", 0), 2)
    daily.append({
        "date":        d,
        "steps":       steps_all.get(d),
        "sleep":       sl.get("score"),
        "sleep_total": total_h or None,
        "sleep_deep":  sl.get("deep"),
        "sleep_light": sl.get("light"),
        "sleep_rem":   sl.get("rem"),
        "sleep_awake": sl.get("awake"),
        "sleep_start": sl.get("start"),
        "sleep_end":   sl.get("end"),
        "hr":          hc.get("hr"),
        "active_cal":  hc.get("active_cal"),
        "total_cal":   hc.get("total_cal"),
    })

print(f"合併後資料：{len(daily)} 筆  ({all_dates[0]} ~ {all_dates[-1]})")

# ── 輸出 HTML ─────────────────────────────────────────────
DAILY_JSON  = json.dumps(daily,         ensure_ascii=False, separators=(",", ":"))
HOURLY_JSON = json.dumps(steps_hourly,  ensure_ascii=False, separators=(",", ":"))

HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>健康儀表板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d0d0d;color:#fff;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',Helvetica,sans-serif;min-height:100vh}
h1{text-align:center;padding:28px 0 4px;font-size:22px;font-weight:700;letter-spacing:.3px}
.sub{text-align:center;color:#666;font-size:12px;margin-bottom:20px}
/* view tabs */
.tabs{display:flex;justify-content:center;gap:6px;margin-bottom:16px}
.tabs button{padding:7px 18px;border:none;border-radius:20px;font-size:13px;font-weight:500;cursor:pointer;background:#1c1c1e;color:#888;transition:all .2s}
.tabs button.active{background:#30d158;color:#000}
/* nav row */
.nav-row{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:22px}
.nav-btn{background:#1c1c1e;border:none;color:#fff;font-size:20px;width:36px;height:36px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .2s}
.nav-btn:hover{background:#2c2c2e}
.nav-btn:disabled{opacity:.3;cursor:default}
#period-wrap{min-width:200px;text-align:center;cursor:pointer}
#period-label{font-size:16px;font-weight:600;display:inline-block;border-bottom:1px dotted #444;padding-bottom:1px}
#period-label:hover{border-color:#888}
#period-input{display:none;background:#2c2c2e;border:1.5px solid #5e8ef7;border-radius:10px;color:#fff;font-size:15px;font-weight:600;text-align:center;padding:5px 14px;width:230px;outline:none}
.period-hint{font-size:10px;color:#555;text-align:center;margin-top:4px;min-height:14px}
/* calendar popup */
#period-wrap{position:relative}
#cal-popup{display:none;position:absolute;left:50%;transform:translateX(-50%);top:calc(100% + 8px);background:#1c1c1e;border:1px solid #3a3a3c;border-radius:16px;padding:16px 14px;z-index:200;width:266px;box-shadow:0 12px 40px rgba(0,0,0,.7)}
#cal-popup.show{display:block}
.cal-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.cal-hdr span{font-size:14px;font-weight:600;color:#fff}
.cal-nav{background:none;border:none;color:#666;font-size:18px;cursor:pointer;width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center}
.cal-nav:hover{color:#fff;background:#2c2c2e}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}
.cal-wd{text-align:center;font-size:10px;color:#555;padding:3px 0 6px}
.cal-wd:first-child{color:#e05c5c}
.cal-wd:last-child{color:#5b8fff}
.cal-d{text-align:center;padding:5px 0 2px;border-radius:8px;font-size:13px;cursor:pointer;color:#666;min-height:30px}
.cal-d.has{color:#ccc}.cal-d.has:hover{background:#2c2c2e}
.cal-d.sel{background:#30d158!important;color:#000;font-weight:700}
.cal-d.today{outline:1px solid #444}
.cal-d.empty{cursor:default}
.cal-dot{width:4px;height:4px;border-radius:50%;background:#30d158;margin:2px auto 0}
.cal-d.sel .cal-dot{background:#000}
/* cards */
.cards{display:grid;grid-template-columns:1fr 1fr;gap:20px;max-width:1100px;margin:0 auto 40px;padding:0 20px}
.card{background:#1c1c1e;border-radius:18px;padding:22px;cursor:default}
.card-head{display:flex;align-items:baseline;gap:8px;margin-bottom:2px}
.card-icon{font-size:14px}
.card-label{font-size:12px;font-weight:600;letter-spacing:1.2px;text-transform:uppercase}
.card-val{font-size:38px;font-weight:700;margin:4px 0 2px}
.card-desc{font-size:12px;color:#888;margin-bottom:16px}
.chart-wrap{position:relative;height:200px}
.stat-row{display:flex;justify-content:space-between;margin-top:14px;padding-top:14px;border-top:1px solid #2c2c2e}
.stat-item{text-align:center;flex:1}
.stat-lbl{font-size:11px;color:#666;margin-bottom:3px}
.stat-num{font-size:15px;font-weight:600}
/* day view */
.day-view{display:none;max-width:1100px;margin:0 auto;padding:0 20px 40px}
.day-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.day-card{background:#1c1c1e;border-radius:18px;padding:24px}
.day-big{font-size:52px;font-weight:700;line-height:1}
.day-unit{font-size:16px;font-weight:400;color:#888}
.sleep-bars{margin-top:16px}
.sleep-bar-row{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.sleep-bar-label{font-size:12px;color:#888;width:40px;text-align:right}
.sleep-bar-track{flex:1;height:8px;background:#2c2c2e;border-radius:4px;overflow:hidden}
.sleep-bar-fill{height:100%;border-radius:4px;transition:width .4s}
.sleep-bar-val{font-size:12px;color:#ccc;width:36px}
.day-stats{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}
.day-stat{background:#2c2c2e;border-radius:12px;padding:12px}
.day-stat-lbl{font-size:11px;color:#888;margin-bottom:4px}
.day-stat-val{font-size:18px;font-weight:600}
/* modal */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:100;justify-content:center;align-items:center}
.modal-bg.open{display:flex}
.modal{background:#1c1c1e;border-radius:22px;padding:28px;width:340px;max-width:90vw;position:relative}
.modal-close{position:absolute;top:16px;right:16px;background:#2c2c2e;border:none;color:#fff;width:28px;height:28px;border-radius:50%;cursor:pointer;font-size:16px}
.modal-date{font-size:13px;color:#888;margin-bottom:16px}
.modal-row{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid #2c2c2e;font-size:14px}
.modal-row:last-child{border-bottom:none}
.modal-row .val{font-weight:600}
.g{color:#30d158}.b{color:#5e8ef7}.o{color:#ff9f0a}.r{color:#ff6b6b}
/* insights */
.insights-wrap{max-width:1100px;margin:0 auto 22px;padding:0 20px}
.insights-title{font-size:11px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:#555;margin-bottom:10px}
.insights-row{display:flex;gap:10px;overflow-x:auto;scrollbar-width:none;padding-bottom:4px}
.insights-row::-webkit-scrollbar{display:none}
.ic{background:#1c1c1e;border-radius:14px;padding:14px 16px;min-width:160px;max-width:200px;flex-shrink:0;border-left:3px solid #333}
.ic.good{border-color:#30d158}.ic.warn{border-color:#ff9f0a}.ic.bad{border-color:#ff6b6b}.ic.info{border-color:#5e8ef7}.ic.tip{border-color:#bf5af2}
.ic-title{font-size:10px;color:#888;letter-spacing:.5px;margin-bottom:4px}
.ic-val{font-size:19px;font-weight:700;line-height:1.2}
.ic-desc{font-size:10px;color:#777;margin-top:5px;line-height:1.4}
.ic.good .ic-val{color:#30d158}.ic.warn .ic-val{color:#ff9f0a}.ic.bad .ic-val{color:#ff6b6b}.ic.info .ic-val{color:#5e8ef7}.ic.tip .ic-val{color:#bf5af2}
/* range picker */
.range-wrap{display:none;max-width:1100px;margin:-8px auto 20px;padding:0 20px}
.range-presets{display:flex;justify-content:center;gap:8px;margin-bottom:12px;flex-wrap:wrap}
.range-presets button{padding:6px 16px;border:none;border-radius:16px;font-size:13px;font-weight:500;cursor:pointer;background:#1c1c1e;color:#888;transition:all .2s}
.range-presets button.active{background:#5e8ef7;color:#000}
.range-inputs{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap}
.range-inputs label{font-size:12px;color:#888}
.range-inputs input[type=date]{background:#1c1c1e;border:1px solid #3c3c3e;border-radius:8px;color:#fff;font-size:13px;padding:6px 10px;outline:none;cursor:pointer}
.range-inputs input[type=date]:focus{border-color:#5e8ef7}
.range-sep{color:#555;font-size:16px}
@media(max-width:640px){.cards,.day-grid{grid-template-columns:1fr}.day-stats{grid-template-columns:1fr 1fr}}
.upd-wrap{text-align:center;margin:-4px 0 16px}
.upd-btn{background:#1c1c1e;border:1px solid #3c3c3e;color:#ccc;padding:8px 22px;border-radius:20px;font-size:13px;cursor:pointer;transition:all .2s}
.upd-btn:hover:not(:disabled){background:#2c2c2e;border-color:#555;color:#fff}
.upd-btn:disabled{opacity:.5;cursor:default}
.upd-sts{font-size:11px;color:#666;margin-top:5px;min-height:14px}
</style>
</head>
<body>
<h1>健康儀表板</h1>
<p class="sub" id="date-range">Garmin Connect 數據</p>
<p style="font-size:11px;color:#888;margin:0 0 8px">資料更新：{fetched_at}</p>

<div class="upd-wrap">
  <button class="upd-btn" id="upd-btn" onclick="triggerUpdate()">↻ 立即更新</button>
  <div class="upd-sts" id="upd-sts"></div>
</div>

<div class="tabs">
  <button onclick="setView('day')"    id="tab-day">日</button>
  <button onclick="setView('week')"   id="tab-week">週</button>
  <button onclick="setView('month')"  id="tab-month" class="active">月</button>
  <button onclick="setView('year')"   id="tab-year">年</button>
  <button onclick="setView('all')"    id="tab-all">全部</button>
  <button onclick="setView('custom')" id="tab-custom">區間</button>
</div>

<div class="nav-row">
  <button class="nav-btn" id="nav-prev" onclick="navPrev()">&#8249;</button>
  <div id="period-wrap">
    <div id="period-label" onclick="startEditPeriod()" title="點擊輸入日期">—</div>
    <input id="period-input" type="text"
      onkeydown="handlePeriodKey(event)"
      onblur="endEditPeriod(false)" />
    <div class="period-hint" id="period-hint"></div>
    <div id="cal-popup">
      <div class="cal-hdr">
        <button class="cal-nav" onclick="calNav(-1);event.stopPropagation()">&#8249;</button>
        <span id="cal-title"></span>
        <button class="cal-nav" onclick="calNav(1);event.stopPropagation()">&#8250;</button>
      </div>
      <div class="cal-grid">
        <div class="cal-wd">日</div><div class="cal-wd">一</div><div class="cal-wd">二</div>
        <div class="cal-wd">三</div><div class="cal-wd">四</div><div class="cal-wd">五</div>
        <div class="cal-wd">六</div>
      </div>
      <div class="cal-grid" id="cal-days"></div>
    </div>
  </div>
  <button class="nav-btn" id="nav-next" onclick="navNext()">&#8250;</button>
</div>

<!-- 區間選擇器 -->
<div class="range-wrap" id="range-wrap">
  <div class="range-presets">
    <button onclick="setRangePreset(1)"  id="rp-1">1 個月</button>
    <button onclick="setRangePreset(3)"  id="rp-3">3 個月</button>
    <button onclick="setRangePreset(6)"  id="rp-6" class="active">半年</button>
    <button onclick="setRangePreset(12)" id="rp-12">1 年</button>
    <button onclick="setRangePreset(0)"  id="rp-0">自訂</button>
  </div>
  <div class="range-inputs">
    <label>從</label>
    <input type="date" id="range-start" onchange="onRangeInput()">
    <span class="range-sep">—</span>
    <label>到</label>
    <input type="date" id="range-end" onchange="onRangeInput()">
  </div>
</div>

<!-- 洞察建議 -->
<div class="insights-wrap">
  <div class="insights-title">洞察建議</div>
  <div class="insights-row" id="insights-row"></div>
</div>

<!-- 日 view -->
<div class="day-view" id="day-view">
  <div class="day-grid">
    <div class="day-card">
      <div style="font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:#30d158;margin-bottom:8px">步數</div>
      <div class="day-big g" id="dv-steps">—</div>
      <div style="font-size:13px;color:#888;margin-top:4px" id="dv-steps-sub"></div>
      <div class="day-stats">
        <div class="day-stat"><div class="day-stat-lbl">心率</div><div class="day-stat-val g" id="dv-hr">—</div></div>
        <div class="day-stat"><div class="day-stat-lbl">活動卡路里</div><div class="day-stat-val g" id="dv-cal">—</div></div>
      </div>
    </div>
    <div class="day-card">
      <div style="font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:#5e8ef7;margin-bottom:8px">睡眠評分</div>
      <div class="day-big b" id="dv-sleep">—</div>
      <div style="font-size:13px;color:#888;margin-top:4px" id="dv-sleep-time"></div>
      <div class="sleep-bars" id="dv-sleep-bars"></div>
    </div>
  </div>
  <!-- 每小時步數分布 -->
  <div class="day-card" id="hourly-card" style="margin-top:20px">
    <div style="font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:#30d158;margin-bottom:12px">步數時段分布</div>
    <div style="position:relative;height:160px"><canvas id="hourlyChart"></canvas></div>
    <div id="hourly-nodata" style="display:none;color:#555;font-size:13px;padding:20px 0;text-align:center">此日無詳細時段資料（僅保留近 7 天）</div>
  </div>
</div>

<!-- 圖表 view -->
<div class="cards" id="chart-view">
  <div class="card">
    <div class="card-head">
      <span class="card-label g">步數</span>
    </div>
    <div class="card-val g" id="steps-val">—</div>
    <div class="card-desc" id="steps-desc">—</div>
    <div class="chart-wrap"><canvas id="stepsChart"></canvas></div>
    <div class="stat-row">
      <div class="stat-item"><div class="stat-lbl">最高單日</div><div class="stat-num g" id="s-max">—</div></div>
      <div class="stat-item"><div class="stat-lbl">達標天數 ≥1萬</div><div class="stat-num g" id="s-goal">—</div></div>
      <div class="stat-item"><div class="stat-lbl">期間合計</div><div class="stat-num g" id="s-total">—</div></div>
    </div>
  </div>
  <div class="card">
    <div class="card-head">
      <span class="card-label b">睡眠評分</span>
    </div>
    <div class="card-val b" id="sleep-val">—</div>
    <div class="card-desc" id="sleep-desc">—</div>
    <div class="chart-wrap"><canvas id="sleepChart"></canvas></div>
    <div class="stat-row">
      <div class="stat-item"><div class="stat-lbl">最高評分</div><div class="stat-num b" id="sl-max">—</div></div>
      <div class="stat-item"><div class="stat-lbl">優質夜 ≥75分</div><div class="stat-num b" id="sl-good">—</div></div>
      <div class="stat-item"><div class="stat-lbl">平均時長</div><div class="stat-num b" id="sl-dur">—</div></div>
    </div>
  </div>
</div>

<!-- 詳細資訊 Modal -->
<div class="modal-bg" id="modal-bg" onclick="closeModal(event)">
  <div class="modal" id="modal">
    <button class="modal-close" onclick="document.getElementById('modal-bg').classList.remove('open')">×</button>
    <div class="modal-date" id="modal-date"></div>
    <div id="modal-rows"></div>
  </div>
</div>

<script>
const DAILY = """ + DAILY_JSON + r""";
const STEPS_HOURLY = """ + HOURLY_JSON + r""";

// 建立日期索引
const byDate = {};
DAILY.forEach(r => { byDate[r.date] = r; });

const lastDate = DAILY.length ? DAILY[DAILY.length-1].date : new Date().toISOString().slice(0,10);
const firstDate = DAILY.length ? DAILY[0].date : lastDate;

// 更新標題
document.getElementById('date-range').textContent =
  `Garmin Connect · ${firstDate} — ${lastDate}`;

let currentView = 'month';
let anchor = new Date(lastDate);
let stepsChart = null, sleepChart = null, hourlyChart = null;
let rangeStart = null, rangeEnd = null, activePreset = 6;

// ── 日期工具 ─────────────────────────────────────────────
function dateStr(d) {
  return d.toISOString().slice(0,10);
}
function addDays(d, n) {
  const r = new Date(d); r.setDate(r.getDate() + n); return r;
}
function fmtNum(n) {
  if (n == null) return '—';
  if (n >= 10000) return (n/10000).toFixed(1) + ' 萬';
  return n.toLocaleString();
}
function fmtH(h) {
  if (h == null || h === 0) return '—';
  const hr = Math.floor(h), mn = Math.round((h - hr) * 60);
  return mn ? `${hr}h ${mn}m` : `${hr}h`;
}
function fmtTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts + 8*3600*1000); // GMT+8
  return d.toISOString().slice(11,16);
}

// ── 取得視圖的資料範圍 ────────────────────────────────────
function getViewDates() {
  if (currentView === 'day') {
    return [dateStr(anchor)];
  } else if (currentView === 'week') {
    const mon = new Date(anchor);
    mon.setDate(mon.getDate() - (mon.getDay() || 7) + 1);
    return Array.from({length:7}, (_,i) => dateStr(addDays(mon, i)));
  } else if (currentView === 'month') {
    const y = anchor.getFullYear(), m = anchor.getMonth();
    const days = new Date(y, m+1, 0).getDate();
    return Array.from({length:days}, (_,i) => dateStr(new Date(y, m, i+1)));
  } else if (currentView === 'year') {
    const y = anchor.getFullYear();
    return Array.from({length:12}, (_,i) => `${y}-${String(i+1).padStart(2,'0')}`);
  } else if (currentView === 'custom') {
    if (!rangeStart || !rangeEnd) return [];
    const dates = [];
    let cur = new Date(rangeStart);
    const end = new Date(rangeEnd);
    while (cur <= end) { dates.push(dateStr(cur)); cur = addDays(cur, 1); }
    return dates;
  } else {
    // 全部：所有月份
    const months = new Set();
    DAILY.forEach(r => months.add(r.date.slice(0,7)));
    return [...months].sort();
  }
}

function getPeriodLabel() {
  if (currentView === 'custom') {
    if (!rangeStart || !rangeEnd) return '選擇區間';
    return `${rangeStart} — ${rangeEnd}`;
  }
  const WD = ['日','一','二','三','四','五','六'];
  if (currentView === 'day') {
    const d = anchor;
    return `${d.getFullYear()} 年 ${d.getMonth()+1} 月 ${d.getDate()} 日（${WD[d.getDay()]}）`;
  } else if (currentView === 'week') {
    const mon = new Date(anchor);
    mon.setDate(mon.getDate() - (mon.getDay() || 7) + 1);
    const sun = addDays(mon, 6);
    return `${mon.getMonth()+1}/${mon.getDate()} — ${sun.getMonth()+1}/${sun.getDate()}`;
  } else if (currentView === 'month') {
    return `${anchor.getFullYear()} 年 ${anchor.getMonth()+1} 月`;
  } else if (currentView === 'year') {
    return `${anchor.getFullYear()} 年`;
  } else {
    return `全部資料（${firstDate.slice(0,7)} — ${lastDate.slice(0,7)}）`;
  }
}

// ── 導航 ─────────────────────────────────────────────────
function navPrev() {
  if (currentView === 'day')   anchor = addDays(anchor, -1);
  else if (currentView === 'week')  anchor = addDays(anchor, -7);
  else if (currentView === 'month') anchor = new Date(anchor.getFullYear(), anchor.getMonth()-1, 1);
  else if (currentView === 'year')  anchor = new Date(anchor.getFullYear()-1, 0, 1);
  render();
}
function navNext() {
  if (currentView === 'day')   anchor = addDays(anchor, 1);
  else if (currentView === 'week')  anchor = addDays(anchor, 7);
  else if (currentView === 'month') anchor = new Date(anchor.getFullYear(), anchor.getMonth()+1, 1);
  else if (currentView === 'year')  anchor = new Date(anchor.getFullYear()+1, 0, 1);
  render();
}

// ── 區間視圖 ──────────────────────────────────────────────
function setRangePreset(months) {
  activePreset = months;
  [1,3,6,12,0].forEach(m => {
    const el = document.getElementById('rp-'+m);
    if (el) el.classList.toggle('active', m === months);
  });
  const end = new Date(lastDate + 'T12:00:00');
  let start;
  if (months === 0) {
    // 自訂：不動日期，只讓使用者手動填
    syncRangeInputs();
    return;
  }
  start = new Date(end);
  start.setMonth(start.getMonth() - months);
  rangeStart = dateStr(start);
  rangeEnd   = dateStr(end);
  syncRangeInputs();
  render();
}

function syncRangeInputs() {
  if (rangeStart) document.getElementById('range-start').value = rangeStart;
  if (rangeEnd)   document.getElementById('range-end').value   = rangeEnd;
}

function onRangeInput() {
  const s = document.getElementById('range-start').value;
  const e = document.getElementById('range-end').value;
  if (s && e && s <= e) {
    rangeStart = s; rangeEnd = e;
    activePreset = 0;
    [1,3,6,12,0].forEach(m => {
      const el = document.getElementById('rp-'+m);
      if (el) el.classList.toggle('active', m === 0);
    });
    render();
  }
}

// ── 視圖切換 ─────────────────────────────────────────────
function setView(v) {
  currentView = v;
  ['day','week','month','year','all','custom'].forEach(x => {
    document.getElementById('tab-'+x).classList.toggle('active', x === v);
  });
  const hideNav = v === 'all' || v === 'custom';
  document.getElementById('nav-prev').style.visibility = hideNav ? 'hidden' : '';
  document.getElementById('nav-next').style.visibility = hideNav ? 'hidden' : '';
  document.getElementById('range-wrap').style.display  = v === 'custom' ? 'block' : 'none';

  // 初始化區間
  if (v === 'custom' && !rangeStart) setRangePreset(6);
  render();
}

// ── 日視圖 ────────────────────────────────────────────────
function renderDay() {
  document.getElementById('day-view').style.display = 'block';
  document.getElementById('chart-view').style.display = 'none';
  const d = dateStr(anchor);
  const r = byDate[d] || {};

  // steps
  document.getElementById('dv-steps').textContent = r.steps != null ? r.steps.toLocaleString() : '—';
  const avgSteps = Math.round(DAILY.filter(x=>x.steps).reduce((a,b)=>a+b.steps,0) / DAILY.filter(x=>x.steps).length);
  const diff = r.steps != null ? r.steps - avgSteps : null;
  document.getElementById('dv-steps-sub').textContent = diff != null
    ? (diff >= 0 ? `+${diff.toLocaleString()} 高於平均` : `${diff.toLocaleString()} 低於平均`)
    : '無資料';

  document.getElementById('dv-hr').textContent  = r.hr  ? r.hr + ' bpm' : '—';
  document.getElementById('dv-cal').textContent = r.active_cal ? Math.round(r.active_cal) + ' kcal' : '—';

  // sleep
  document.getElementById('dv-sleep').textContent = r.sleep ?? '—';
  const st = r.sleep_start ? fmtTime(r.sleep_start) : '—';
  const en = r.sleep_end   ? fmtTime(r.sleep_end)   : '—';
  document.getElementById('dv-sleep-time').textContent = r.sleep_total
    ? `${st} — ${en}  共 ${fmtH(r.sleep_total)}`
    : '無資料';

  const maxH = 8;
  const bars = [
    {lbl:'深層', val:r.sleep_deep, color:'#5e8ef7'},
    {lbl:'淺層', val:r.sleep_light, color:'#7eb3ff'},
    {lbl:'REM',  val:r.sleep_rem,  color:'#bf5af2'},
    {lbl:'清醒', val:r.sleep_awake, color:'#ff9f0a'},
  ];
  document.getElementById('dv-sleep-bars').innerHTML = bars.map(b => `
    <div class="sleep-bar-row">
      <div class="sleep-bar-label">${b.lbl}</div>
      <div class="sleep-bar-track">
        <div class="sleep-bar-fill" style="width:${b.val?Math.min(b.val/maxH*100,100):0}%;background:${b.color}"></div>
      </div>
      <div class="sleep-bar-val">${b.val ? fmtH(b.val) : '—'}</div>
    </div>`).join('');

  renderHourlySteps(d);
}

// ── 每小時步數圖 ──────────────────────────────────────────
function renderHourlySteps(dateStr) {
  const canvas  = document.getElementById('hourlyChart');
  const nodata  = document.getElementById('hourly-nodata');
  const hourly  = STEPS_HOURLY[dateStr];

  if (hourlyChart) { hourlyChart.destroy(); hourlyChart = null; }

  if (!hourly) {
    canvas.style.display = 'none';
    nodata.style.display = 'block';
    return;
  }
  canvas.style.display = 'block';
  nodata.style.display = 'none';

  const labels = Array.from({length:24}, (_,i) => i);
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 160);
  gradient.addColorStop(0, '#30d15866');
  gradient.addColorStop(1, '#30d15800');

  hourlyChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: hourly,
        backgroundColor: hourly.map(v => v > 0 ? '#30d158cc' : '#2c2c2e'),
        borderColor:     hourly.map(v => v > 0 ? '#30d158'   : '#3c3c3e'),
        borderWidth: 1,
        borderRadius: 3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1c1c1e',
          borderColor: '#3c3c3e',
          borderWidth: 1,
          titleColor: '#ccc',
          bodyColor: '#fff',
          callbacks: {
            title: items => `${items[0].label}:00 — ${items[0].label}:59`,
            label: c => '步數：' + (c.raw > 0 ? c.raw.toLocaleString() + ' 步' : '—')
          }
        }
      },
      scales: {
        x: {
          grid: { color: '#1a1a1a' },
          ticks: {
            color: '#555',
            font: { size: 10 },
            callback: (_, i) => i % 3 === 0 ? i : ''
          }
        },
        y: {
          grid: { color: '#222' },
          min: 0,
          ticks: {
            color: '#555',
            font: { size: 10 },
            maxTicksLimit: 4,
            callback: v => v >= 1000 ? (v/1000).toFixed(1)+'k' : v
          }
        }
      }
    }
  });
}

// ── 圖表視圖 ──────────────────────────────────────────────
function renderCharts() {
  document.getElementById('day-view').style.display = 'none';
  document.getElementById('chart-view').style.display = 'grid';

  const dates = getViewDates();
  const isMonthly = (currentView === 'year' || currentView === 'all');
  const isCustom  = (currentView === 'custom');

  // 聚合資料
  let chartData;
  if (isMonthly) {
    // 按月聚合
    const mSteps = {}, mSleep = {}, mSleepT = {};
    dates.forEach(ym => { mSteps[ym]=[]; mSleep[ym]=[]; mSleepT[ym]=[]; });
    DAILY.forEach(r => {
      const ym = r.date.slice(0,7);
      if (!dates.includes(ym)) return;
      if (r.steps != null) mSteps[ym].push(r.steps);
      if (r.sleep != null) { mSleep[ym].push(r.sleep); }
      if (r.sleep_total != null && r.sleep_total > 0) mSleepT[ym].push(r.sleep_total);
    });
    chartData = dates.map(ym => ({
      label: ym,
      steps: mSteps[ym].length ? Math.round(mSteps[ym].reduce((a,b)=>a+b,0)/mSteps[ym].length) : null,
      steps_total: mSteps[ym].reduce((a,b)=>a+b,0),
      sleep: mSleep[ym].length ? Math.round(mSleep[ym].reduce((a,b)=>a+b,0)/mSleep[ym].length*10)/10 : null,
      sleep_total: mSleepT[ym].length ? Math.round(mSleepT[ym].reduce((a,b)=>a+b,0)/mSleepT[ym].length*10)/10 : null,
      days: mSteps[ym].length,
    }));
  } else {
    // 每日資料
    chartData = dates.map(d => {
      const r = byDate[d] || {};
      return {
        label: d,
        steps: r.steps ?? null,
        steps_total: r.steps ?? null,
        sleep: r.sleep ?? null,
        sleep_total: r.sleep_total ?? null,
        ...r,
      };
    });
  }

  // 統計
  const svs = chartData.filter(r=>r.steps!=null).map(r=>r.steps);
  const slvs = chartData.filter(r=>r.sleep!=null).map(r=>r.sleep);
  const durVs = chartData.filter(r=>r.sleep_total>0).map(r=>r.sleep_total);

  const avgS = svs.length ? Math.round(svs.reduce((a,b)=>a+b,0)/svs.length) : null;
  const maxS = svs.length ? Math.max(...svs) : null;
  const goalDays = isMonthly
    ? chartData.filter(r => r.steps != null && r.steps >= 10000).length
    : chartData.filter(r => r.steps >= 10000).length;
  const totalS = chartData.reduce((a,r)=>a+(r.steps_total||0),0);

  const avgSl = slvs.length ? Math.round(slvs.reduce((a,b)=>a+b,0)/slvs.length*10)/10 : null;
  const maxSl = slvs.length ? Math.max(...slvs) : null;
  const goodN = slvs.filter(v=>v>=75).length;
  const avgDur = durVs.length ? Math.round(durVs.reduce((a,b)=>a+b,0)/durVs.length*10)/10 : null;

  document.getElementById('steps-val').textContent = fmtNum(avgS);
  document.getElementById('steps-desc').textContent = isMonthly ? '月平均每日步數' : '期間平均每日步數';
  document.getElementById('s-max').textContent    = fmtNum(maxS);
  document.getElementById('s-goal').textContent   = goalDays + (isMonthly ? ' 月' : ' 天');
  document.getElementById('s-total').textContent  = fmtNum(totalS);

  document.getElementById('sleep-val').textContent  = avgSl ?? '—';
  document.getElementById('sleep-desc').textContent = '平均睡眠評分（滿分 100）';
  document.getElementById('sl-max').textContent  = maxSl ?? '—';
  document.getElementById('sl-good').textContent = goodN + (isMonthly ? ' 月' : ' 天');
  document.getElementById('sl-dur').textContent  = avgDur ? fmtH(avgDur) : '—';

  // 圖表
  if (stepsChart) stepsChart.destroy();
  if (sleepChart) sleepChart.destroy();

  const labels = chartData.map(r => r.label);
  const ptR    = chartData.length > 60 ? 0 : (chartData.length > 20 ? 2 : 4);

  const isAll = (currentView === 'all');

  stepsChart = makeChart('stepsChart', labels,
    chartData.map(r => r.steps),
    '#30d158', '步數', null, '步數',
    v => v >= 10000 ? (v/10000).toFixed(1)+'萬' : v.toLocaleString(),
    chartData, isMonthly, isAll);

  sleepChart = makeChart('sleepChart', labels,
    chartData.map(r => r.sleep),
    '#5e8ef7', '睡眠評分', 100, '睡眠評分',
    v => v, chartData, isMonthly, isAll);
}

// ── 日期格式化工具 ────────────────────────────────────────
const WD = ['日','一','二','三','四','五','六'];
function fmtLabel(lbl) {
  if (!lbl) return '—';
  if (lbl.length === 7) {
    const [y, m] = lbl.split('-');
    return `${y}年${parseInt(m)}月`;
  }
  const d = new Date(lbl + 'T12:00:00');
  return `${d.getFullYear()}年${d.getMonth()+1}月${d.getDate()}日（週${WD[d.getDay()]}）`;
}
function fmtTick(lbl) {
  if (lbl.length === 7) {
    return parseInt(lbl.slice(5)) + '月';
  }
  const d = new Date(lbl + 'T12:00:00');
  return `${d.getMonth()+1}/${d.getDate()}`;
}

function makeHLinePlugin(tickFmt) {
  return {
    id: 'hline',
    afterDraw(chart) {
      const active = chart.tooltip._active;
      if (!active || !active.length) return;
      const el = active[0].element;
      if (!el || isNaN(el.y)) return;
      const {ctx, chartArea: {left, right}} = chart;
      const yVal = chart.scales.y.getValueForPixel(el.y);
      ctx.save();
      // 水平虛線
      ctx.beginPath();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = 'rgba(255,255,255,0.22)';
      ctx.lineWidth = 1;
      ctx.moveTo(left, el.y);
      ctx.lineTo(right, el.y);
      ctx.stroke();
      // 左側數值標籤
      const lbl = String(tickFmt ? tickFmt(yVal) : Math.round(yVal));
      ctx.setLineDash([]);
      ctx.font = '11px -apple-system,sans-serif';
      const tw = ctx.measureText(lbl).width + 10;
      ctx.fillStyle = 'rgba(44,44,46,0.92)';
      ctx.fillRect(left - tw - 4, el.y - 9, tw, 18);
      ctx.fillStyle = '#bbb';
      ctx.textAlign = 'right';
      ctx.fillText(lbl, left - 6, el.y + 4);
      ctx.restore();
    }
  };
}

function makeChart(id, labels, vals, color, label, yMax, tipLabel, tickFmt, rawData, isMonthly, isAll) {
  const ctx = document.getElementById(id).getContext('2d');
  const ptR = vals.length > 60 ? 0 : vals.length > 20 ? 2 : 4;
  // Pre-compute first index of each year (for isAll year labels)
  const yearFirst = {};
  labels.forEach((lbl, i) => {
    if (lbl && lbl.length === 7) {
      const y = lbl.slice(0, 4);
      if (!(y in yearFirst)) yearFirst[y] = i;
    }
  });

  const gradient = ctx.createLinearGradient(0, 0, 0, 200);
  gradient.addColorStop(0, color + '44');
  gradient.addColorStop(1, color + '00');

  const chart = new Chart(ctx, {
    type: 'line',
    plugins: [makeHLinePlugin(tickFmt)],
    data: {
      labels,
      datasets: [{
        label, data: vals,
        borderColor: color,
        backgroundColor: gradient,
        borderWidth: 2,
        pointRadius: ptR,
        pointHoverRadius: 7,
        pointBackgroundColor: color,
        fill: true,
        tension: 0.35,
        spanGaps: true,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode:'index', intersect:false },
      onClick(evt, elems) {
        if (!elems.length) return;
        const idx = elems[0].index;
        const rd = rawData[idx];
        if (!rd) return;
        if (isMonthly) {
          showMonthlyModal(rd);
        } else {
          showDailyModal(rd.label || rd.date, rd);
        }
      },
      plugins: {
        legend: { display:false },
        tooltip: {
          backgroundColor:'#1c1c1e',
          borderColor:'#3c3c3e',
          borderWidth:1,
          titleColor:'#ccc',
          bodyColor:'#fff',
          padding:12,
          callbacks: {
            title: items => fmtLabel(items[0].label),
            label: c => tipLabel + ': ' + (c.raw != null ? tickFmt(c.raw) : '—')
          }
        }
      },
      scales: {
        x: {
          grid: { color:'#222' },
          ticks: {
            color:'#555',
            autoSkip: !isAll,
            maxTicksLimit: isAll ? 999 : (labels.length <= 12 ? labels.length : 10),
            font:{size:11},
            callback: (val, idx) => {
              const lbl = labels[idx] || '';
              if (isAll && lbl.length === 7) {
                const y = lbl.slice(0, 4);
                // 全部視圖：每年第一筆資料點顯示年份標籤
                return yearFirst[y] === idx ? y + '年' : null;
              }
              return fmtTick(lbl);
            }
          }
        },
        y: {
          grid: { color:'#222' },
          min: 0,
          max: yMax || undefined,
          ticks: {
            color:'#555',
            font:{size:11},
            callback: v => tickFmt(v)
          }
        }
      }
    }
  });
  return chart;
}

// ── Modal ─────────────────────────────────────────────────
function openModal(title, rows) {
  document.getElementById('modal-date').textContent = title;
  document.getElementById('modal-rows').innerHTML = rows
    .map(([lbl, val, cls]) =>
      `<div class="modal-row"><span>${lbl}</span><span class="val ${cls||''}">${val}</span></div>`)
    .join('');
  document.getElementById('modal-bg').classList.add('open');
}

function showDailyModal(dateLabel, r) {
  openModal(fmtLabel(dateLabel), [
    ['步數',       r.steps != null ? r.steps.toLocaleString() + ' 步' : '—', 'g'],
    ['睡眠評分',   r.sleep != null ? r.sleep + ' 分' : '—', 'b'],
    ['深層睡眠',   r.sleep_deep  ? fmtH(r.sleep_deep)  : '—', 'b'],
    ['淺層睡眠',   r.sleep_light ? fmtH(r.sleep_light) : '—', 'b'],
    ['REM 睡眠',   r.sleep_rem   ? fmtH(r.sleep_rem)   : '—', 'b'],
    ['清醒時間',   r.sleep_awake ? fmtH(r.sleep_awake) : '—', 'o'],
    ['靜止心率',   r.hr          ? r.hr + ' bpm'        : '—', 'r'],
    ['活動卡路里', r.active_cal  ? Math.round(r.active_cal) + ' kcal' : '—', 'o'],
  ]);
}

function showMonthlyModal(rd) {
  openModal(fmtLabel(rd.label) + '（月統計）', [
    ['日均步數',   rd.steps != null ? fmtNum(rd.steps) + ' 步' : '—', 'g'],
    ['月總步數',   rd.steps_total  ? fmtNum(rd.steps_total) + ' 步' : '—', 'g'],
    ['平均睡眠評分', rd.sleep != null ? rd.sleep + ' 分' : '—', 'b'],
    ['平均睡眠時長', rd.sleep_total  ? fmtH(rd.sleep_total) : '—', 'b'],
    ['有效天數',   (rd.days || '—') + (rd.days ? ' 天' : ''), ''],
  ]);
}

function closeModal(e) {
  if (e.target === document.getElementById('modal-bg'))
    document.getElementById('modal-bg').classList.remove('open');
}

// ── 洞察建議 ──────────────────────────────────────────────
function avg(arr) { return arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : null; }
function pct(val, base) { return base ? Math.round((val - base) / base * 100) : null; }
function trend(delta) { return delta == null ? '' : delta > 0 ? '↑' : delta < 0 ? '↓' : '→'; }
function trendType(delta) { return delta == null ? 'info' : delta >= 5 ? 'good' : delta <= -10 ? 'bad' : 'info'; }

// 取得當前視圖的日資料 + 前一期日資料
function getPeriodDailyData() {
  let currDates = [], prevDates = [];

  if (currentView === 'day') {
    currDates = [dateStr(anchor)];
    prevDates = [dateStr(addDays(anchor, -1))];

  } else if (currentView === 'week') {
    const mon = new Date(anchor);
    mon.setDate(mon.getDate() - (mon.getDay() || 7) + 1);
    currDates = Array.from({length:7}, (_,i) => dateStr(addDays(mon, i)));
    const prevMon = addDays(mon, -7);
    prevDates = Array.from({length:7}, (_,i) => dateStr(addDays(prevMon, i)));

  } else if (currentView === 'month') {
    const y = anchor.getFullYear(), m = anchor.getMonth();
    const days = new Date(y, m+1, 0).getDate();
    currDates = Array.from({length:days}, (_,i) => dateStr(new Date(y, m, i+1)));
    const py = m === 0 ? y-1 : y, pm = m === 0 ? 11 : m-1;
    const pdays = new Date(py, pm+1, 0).getDate();
    prevDates = Array.from({length:pdays}, (_,i) => dateStr(new Date(py, pm, i+1)));

  } else if (currentView === 'year') {
    const y = anchor.getFullYear();
    currDates = DAILY.filter(r=>r.date.startsWith(y+'')).map(r=>r.date);
    prevDates = DAILY.filter(r=>r.date.startsWith((y-1)+'')).map(r=>r.date);

  } else if (currentView === 'custom') {
    currDates = getViewDates();
    prevDates = [];
  } else {
    currDates = DAILY.map(r=>r.date);
    prevDates = [];
  }

  const curr = currDates.map(d=>byDate[d]).filter(Boolean);
  const prev = prevDates.map(d=>byDate[d]).filter(Boolean);
  return {curr, prev};
}

function generateInsights() {
  const cards = [];
  const {curr, prev} = getPeriodDailyData();

  const cSteps  = curr.filter(r=>r.steps>0).map(r=>r.steps);
  const pSteps  = prev.filter(r=>r.steps>0).map(r=>r.steps);
  const cSleep  = curr.filter(r=>r.sleep>0).map(r=>r.sleep);
  const pSleep  = prev.filter(r=>r.sleep>0).map(r=>r.sleep);
  const cDur    = curr.filter(r=>r.sleep_total>0).map(r=>r.sleep_total);

  const avgCS = avg(cSteps), avgPS = avg(pSteps);
  const avgCL = avg(cSleep), avgPL = avg(pSleep);
  const avgCD = avg(cDur);
  const deltaS = pct(avgCS, avgPS);
  const deltaL = pct(avgCL, avgPL);

  const viewLabel = {
    day:'今日', week:'本週', month:'本月', year:'本年', all:'全期'
  }[currentView];
  const prevLabel = {
    day:'昨日', week:'上週', month:'上月', year:'去年', all:''
  }[currentView];

  // ── 步數比較 ──────────────────────────────────────────
  if (avgCS != null) {
    if (currentView === 'day') {
      const s = cSteps[0] || 0;
      const left = 10000 - s;
      if (s >= 10000) {
        cards.push({type:'good', title:'今日達標',
          val: s.toLocaleString() + ' 步',
          desc: `超過1萬步目標 🎉${avgPS ? `　昨日：${Math.round(avgPS).toLocaleString()} 步` : ''}`});
      } else {
        cards.push({type: left > 5000 ? 'bad' : 'warn', title:'今日步數',
          val: s.toLocaleString() + ' 步',
          desc: `還差 ${left.toLocaleString()} 步達標${avgPS ? `　昨日：${Math.round(avgPS).toLocaleString()} 步` : ''}`});
      }
    } else {
      const type = trendType(deltaS);
      cards.push({type, title: viewLabel + '平均步數',
        val: Math.round(avgCS).toLocaleString() + ' 步/日',
        desc: deltaS != null
          ? `${trend(deltaS)} 較${prevLabel} ${deltaS>0?'+':''}${deltaS}%（${prevLabel}均 ${Math.round(avgPS).toLocaleString()}）`
          : '無前期資料可比較'});
    }
  }

  // ── 達標天數 ──────────────────────────────────────────
  if (currentView !== 'day' && currentView !== 'all' && cSteps.length > 0) {
    const hitDays = cSteps.filter(s=>s>=10000).length;
    const ratio = Math.round(hitDays / cSteps.length * 100);
    const type = ratio >= 70 ? 'good' : ratio >= 40 ? 'warn' : 'bad';
    const unit = currentView === 'year' ? '天' : '天';
    cards.push({type, title: viewLabel + '達標率（≥1萬步）',
      val: `${hitDays} / ${cSteps.length} 天`,
      desc: `${ratio}% 的天數達到1萬步目標`});
  }

  // ── 睡眠比較 ──────────────────────────────────────────
  if (avgCL != null) {
    if (currentView === 'day') {
      const s = cSleep[0];
      const q = s >= 80 ? '優質 😊' : s >= 60 ? '普通' : s >= 40 ? '偏差 😴' : '低落 ⚠️';
      const type = s >= 80 ? 'good' : s >= 60 ? 'info' : s >= 40 ? 'warn' : 'bad';
      cards.push({type, title:'今日睡眠評分',
        val: s + ' 分',
        desc: `品質${q}${avgPL ? `　昨日：${Math.round(avgPL)} 分` : ''}`});
    } else {
      const type = trendType(deltaL);
      cards.push({type, title: viewLabel + '平均睡眠評分',
        val: avgCL.toFixed(1) + ' 分',
        desc: deltaL != null
          ? `${trend(deltaL)} 較${prevLabel} ${deltaL>0?'+':''}${deltaL}%（${prevLabel}均 ${avgPL.toFixed(1)} 分）`
          : '無前期資料可比較'});
    }
  }

  // ── 睡眠時長 ──────────────────────────────────────────
  if (avgCD != null) {
    const type = avgCD >= 7 ? 'good' : avgCD >= 6 ? 'info' : 'bad';
    const advice = avgCD < 6 ? '建議每晚至少7小時' : avgCD >= 7 ? '睡眠時間充足' : '略低於建議值（7小時）';
    cards.push({type, title: viewLabel + '平均睡眠時長',
      val: fmtH(avgCD),
      desc: advice});
  }

  // ── 最佳單日（週/月視圖）──────────────────────────────
  if ((currentView === 'week' || currentView === 'month') && cSteps.length > 0) {
    const bestR = curr.filter(r=>r.steps>0).reduce((a,b)=>b.steps>a.steps?b:a);
    cards.push({type:'info', title: viewLabel + '步數最高',
      val: bestR.steps.toLocaleString() + ' 步',
      desc: fmtLabel(bestR.date)});
  }

  // ── 當前連續達標（永遠顯示）────────────────────────────
  let streak = 0;
  for (let i = DAILY.length-1; i >= 0; i--) {
    if ((DAILY[i].steps||0) >= 10000) streak++; else break;
  }
  if (streak > 0) {
    cards.push({type: streak >= 7 ? 'good' : streak >= 3 ? 'info' : 'tip',
      title:'目前連續達標',
      val: streak + ' 天',
      desc: streak >= 7 ? '太棒了！保持每天走1萬步' : streak >= 3 ? '繼續保持，已連續達標' : '加油，爭取連續達標'});
  }

  // ── 全期最長連續 / 個人紀錄（全部 / 年視圖）─────────────
  if (currentView === 'all' || currentView === 'year') {
    const subset = currentView === 'year'
      ? DAILY.filter(r=>r.date.startsWith(anchor.getFullYear()+''))
      : DAILY;
    let maxStr = 0, curStr = 0, strEnd = '';
    for (const r of subset) {
      if ((r.steps||0) >= 10000) { curStr++; if (curStr>maxStr){maxStr=curStr;strEnd=r.date;} }
      else curStr = 0;
    }
    if (maxStr > 0) {
      cards.push({type:'tip', title:(currentView==='year'?'年度':'歷史') + '最長連續達標',
        val: maxStr + ' 天',
        desc: `截至 ${fmtLabel(strEnd).replace('（'+WD[new Date(strEnd+'T12:00:00').getDay()]+'）','')}`});
    }
    const allBest = subset.filter(r=>r.steps>0);
    if (allBest.length) {
      const best = allBest.reduce((a,b)=>b.steps>a.steps?b:a);
      cards.push({type:'info', title:(currentView==='year'?'年度':'歷史') + '步數紀錄',
        val: best.steps.toLocaleString() + ' 步',
        desc: fmtLabel(best.date)});
    }
  }

  // ── 渲染 ─────────────────────────────────────────────
  const row = document.getElementById('insights-row');
  row.innerHTML = cards.length ? cards.map(c => `
    <div class="ic ${c.type}">
      <div class="ic-title">${c.title}</div>
      <div class="ic-val">${c.val}</div>
      <div class="ic-desc">${c.desc}</div>
    </div>`).join('') :
    '<div style="color:#555;font-size:13px;padding:10px">此時間段資料不足</div>';
}

// ── 日期輸入 ──────────────────────────────────────────────
const PERIOD_HINTS = {
  day:    '輸入：YYYY-MM-DD 或 M/D',
  week:   '輸入：YYYY-MM-DD（跳至該週）',
  month:  '輸入：YYYY-MM 或 單純月份（如 4）',
  year:   '輸入：年份（如 2025）',
  all:    '',
  custom: '',
};

function currentPeriodValue() {
  const p = n => String(n).padStart(2,'0');
  if (currentView === 'day')
    return `${anchor.getFullYear()}-${p(anchor.getMonth()+1)}-${p(anchor.getDate())}`;
  if (currentView === 'week') {
    const mon = new Date(anchor);
    mon.setDate(mon.getDate() - (mon.getDay() || 7) + 1);
    return `${mon.getFullYear()}-${p(mon.getMonth()+1)}-${p(mon.getDate())}`;
  }
  if (currentView === 'month')
    return `${anchor.getFullYear()}-${p(anchor.getMonth()+1)}`;
  if (currentView === 'year')
    return `${anchor.getFullYear()}`;
  return '';
}

// ── 月曆 popup ────────────────────────────────────────────
let calY, calM;
function openCal() {
  calY = anchor.getFullYear(); calM = anchor.getMonth();
  renderCal();
  document.getElementById('cal-popup').classList.add('show');
  setTimeout(() => document.addEventListener('click', calOutside), 10);
}
function calOutside(e) {
  if (!document.getElementById('cal-popup').contains(e.target)) closeCal();
}
function closeCal() {
  document.getElementById('cal-popup').classList.remove('show');
  document.removeEventListener('click', calOutside);
}
function calNav(dir) {
  calM += dir;
  if (calM < 0) { calM = 11; calY--; }
  if (calM > 11) { calM = 0; calY++; }
  renderCal();
}
function renderCal() {
  document.getElementById('cal-title').textContent = `${calY}年${calM+1}月`;
  const grid = document.getElementById('cal-days');
  grid.innerHTML = '';
  const firstDow = new Date(calY, calM, 1).getDay();
  const dim      = new Date(calY, calM+1, 0).getDate();
  const todayStr = dateStr(new Date());
  const selStr   = dateStr(anchor);
  for (let i = 0; i < firstDow; i++) {
    const e = document.createElement('div'); e.className='cal-d empty'; grid.appendChild(e);
  }
  for (let d = 1; d <= dim; d++) {
    const ds = `${calY}-${String(calM+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const has = !!(byDate[ds] && (byDate[ds].steps != null || byDate[ds].sleep != null));
    const el  = document.createElement('div');
    el.className = 'cal-d' + (has?' has':'') + (ds===selStr?' sel':'') + (ds===todayStr?' today':'');
    el.innerHTML = d + (has?'<div class="cal-dot"></div>':'');
    el.onclick = (ev) => { ev.stopPropagation(); anchor=new Date(ds+'T12:00:00'); closeCal(); setView('day'); };
    grid.appendChild(el);
  }
}

function startEditPeriod() {
  if (currentView === 'all') return;
  if (currentView === 'day') { openCal(); return; }
  const lbl = document.getElementById('period-label');
  const inp = document.getElementById('period-input');
  const hint = document.getElementById('period-hint');
  lbl.style.display = 'none';
  inp.style.display = 'inline-block';
  inp.placeholder = PERIOD_HINTS[currentView];
  inp.value = currentPeriodValue();
  hint.textContent = PERIOD_HINTS[currentView];
  inp.focus();
  inp.select();
}

function endEditPeriod(apply) {
  const lbl = document.getElementById('period-label');
  const inp = document.getElementById('period-input');
  document.getElementById('period-hint').textContent = '';
  inp.style.display = 'none';
  lbl.style.display = 'inline-block';
  if (apply && inp.value.trim()) parseAndNavigate(inp.value.trim());
}

function handlePeriodKey(e) {
  if (e.key === 'Enter')  { e.preventDefault(); endEditPeriod(true); }
  if (e.key === 'Escape') { e.preventDefault(); endEditPeriod(false); }
}

function parseAndNavigate(val) {
  let d = null;
  val = val.trim();

  if (currentView === 'day' || currentView === 'week') {
    if (/^\d{4}-\d{1,2}-\d{1,2}$/.test(val)) {
      d = new Date(val + 'T12:00:00');
    } else if (/^\d{1,2}\/\d{1,2}(\/\d{4})?$/.test(val)) {
      const p = val.split('/');
      const y = p[2] ? parseInt(p[2]) : anchor.getFullYear();
      d = new Date(y, parseInt(p[0])-1, parseInt(p[1]), 12);
    } else if (/^\d{4}$/.test(val)) {
      d = new Date(parseInt(val), 0, 1, 12);
    }
  } else if (currentView === 'month') {
    if (/^\d{4}-\d{1,2}$/.test(val)) {
      const [y, m] = val.split('-');
      d = new Date(parseInt(y), parseInt(m)-1, 1, 12);
    } else if (/^\d{1,2}$/.test(val)) {
      d = new Date(anchor.getFullYear(), parseInt(val)-1, 1, 12);
    } else if (/^\d{4}$/.test(val)) {
      d = new Date(parseInt(val), anchor.getMonth(), 1, 12);
    }
  } else if (currentView === 'year') {
    if (/^\d{4}$/.test(val)) {
      d = new Date(parseInt(val), 0, 1, 12);
    }
  }

  if (d && !isNaN(d)) {
    anchor = d;
    render();
  }
}

// ── 主渲染 ────────────────────────────────────────────────
function render() {
  document.getElementById('period-label').textContent = getPeriodLabel();
  generateInsights();
  if (currentView === 'day') renderDay();
  else renderCharts();
}

setView('month');

// ── 立即更新 ─────────────────────────────────────────────
(function(){
  const REPO='adam7315/garmin-health', WF='update.yml', KEY='gat';
  // 支援 #setup=TOKEN 一鍵初始化
  (function(){
    const h=location.hash;
    if(h.startsWith('#setup=')){
      const t=h.slice(7);
      if(t){ localStorage.setItem(KEY,t); location.hash=''; }
    }
  })();
  function getToken(){
    return localStorage.getItem(KEY)||null;
  }
  window.triggerUpdate=async function(){
    const btn=document.getElementById('upd-btn');
    const sts=document.getElementById('upd-sts');
    let tok=getToken();
    if(!tok){
      tok=prompt('請輸入 GitHub Personal Access Token\n（需有 workflow 寫入權限，建議 fine-grained PAT）：');
      if(!tok){sts.textContent='已取消';return;}
      localStorage.setItem(KEY,tok);
    }
    btn.disabled=true; btn.textContent='送出中...'; sts.textContent='';
    try{
      const r=await fetch(
        `https://api.github.com/repos/${REPO}/actions/workflows/${WF}/dispatches`,
        {method:'POST',
         headers:{'Authorization':'Bearer '+tok,'Accept':'application/vnd.github+json','Content-Type':'application/json'},
         body:JSON.stringify({ref:'main'})});
      if(r.status===204){
        btn.textContent='✓ 已觸發';
        sts.textContent='約 2-3 分鐘後重新整理頁面即可看到新資料';
        setTimeout(()=>{btn.textContent='↻ 立即更新';btn.disabled=false;sts.textContent='';},200000);
      } else if(r.status===401){
        localStorage.removeItem(KEY);
        sts.textContent='Token 無效，已清除，請再按一次重新輸入';
        btn.textContent='↻ 立即更新'; btn.disabled=false;
      } else if(r.status===404){
        sts.textContent='找不到 workflow（請確認 GitHub runner 是否設定完成）';
        btn.textContent='↻ 立即更新'; btn.disabled=false;
      } else {
        const body=await r.json().catch(()=>({}));
        sts.textContent=`錯誤 ${r.status}：${body.message||'請稍後再試'}`;
        btn.textContent='↻ 立即更新'; btn.disabled=false;
      }
    } catch(e){
      sts.textContent='網路錯誤：'+e.message;
      btn.textContent='↻ 立即更新'; btn.disabled=false;
    }
  };
  // 長按按鈕可清除 Token（重新設定）
  let _lp;
  document.getElementById('upd-btn').addEventListener('pointerdown',()=>{
    _lp=setTimeout(()=>{localStorage.removeItem(KEY);document.getElementById('upd-sts').textContent='Token 已清除，下次按鈕時重新輸入';},1500);
  });
  document.getElementById('upd-btn').addEventListener('pointerup',()=>clearTimeout(_lp));
})();
</script>
</body>
</html>"""

HTML = HTML.replace('{fetched_at}', fetched_at or '（未知）')

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(HTML)

print(f"Done: {OUTPUT}")
