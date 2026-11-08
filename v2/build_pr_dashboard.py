"""Build self-contained interactive P/R research dashboard from same-session CSVs."""
import html
import json
import sys
from pathlib import Path
import pandas as pd

def build(low_path):
    path=Path(low_path)
    low=pd.read_csv(path,dtype={"code":str})
    day=low.date.mode().iloc[0]
    low=low[low.date==day].copy()
    pressure_path=path.parent/f"pressure_{day}.csv"
    p=pd.read_csv(pressure_path,dtype={"code":str})
    p=p[p.date==day][["code","pressure_score"]]
    data=low.merge(p,on="code",how="left",validate="one_to_one")
    for col in ("pressure_score","repair_score","distance_pct","ret_5d_pct","ret_20d_pct"):
        data[col]=pd.to_numeric(data[col],errors="coerce")
    data["exhaustion_watch"]=data.exhaustion_watch.astype(str).str.lower().eq("true")
    cols=["code","name","date","pressure_score","repair_score","repair_stage","exhaustion_watch",
          "distance_pct","ret_5d_pct","ret_20d_pct","quality_status"]
    records=json.loads(data[cols].where(pd.notna(data[cols]),None).to_json(orient="records",force_ascii=False))
    payload=json.dumps(records,ensure_ascii=False).replace("<","\\u003c").replace(">","\\u003e")
    page="""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>P+R 个股抛压与承接观察</title>
<style>body{font:15px system-ui,Arial;margin:0;background:#f5f7fb;color:#17243b}main{max-width:1200px;margin:auto;padding:24px}h1{margin:0 0 8px}p{color:#64748b}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}.stat{background:white;padding:16px 22px;border-radius:12px;min-width:140px}.stat b{display:block;font-size:27px}input,select{padding:10px;border:1px solid #cbd5e1;border-radius:8px;margin:5px}table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;padding:10px;border-bottom:1px solid #edf0f4;white-space:nowrap}th{cursor:pointer;background:#eaf0f7}tr:hover{background:#f1f7ff}.scroll{overflow:auto;border-radius:12px}.pill{border-radius:6px;padding:3px 8px;background:#e5eef8}.meter{height:7px;background:#e5e7eb;border-radius:5px;width:90px;display:inline-block;vertical-align:middle;margin-left:6px}.fill{height:100%;background:#d97706;border-radius:5px}.green{background:#059669}.note{font-size:13px}</style></head><body><main>
<h1>个股抛压 P + 承接 R 仪表盘</h1><p>交易日：__DAY__ · 实验指标，非交易建议。P为同日横截面相对压力，R为未经回测的承接证据分。</p>
<div class="stats"><div class="stat">有效记录<b id="total"></b></div><div class="stat">疑似衰竭<b id="ex"></b></div><div class="stat">初步承接观察<b id="support"></b></div></div>
<input id="search" placeholder="输入股票代码或名称" aria-label="搜索股票">
<select id="stage"><option value="">全部阶段</option><option>初步承接观察</option><option>疑似衰竭待确认</option><option>抛压未见充分缓解</option><option>非下跌修复情境</option></select>
<select id="quality"><option value="">全部财务初筛</option><option value="priority_review">优先复核</option><option value="ordinary_review">常规复核</option></select>
<div class="scroll"><table><thead><tr><th data-key="code">代码</th><th data-key="name">名称</th><th data-key="pressure_score">P 压力分</th><th data-key="repair_score">R 承接分</th><th data-key="repair_stage">阶段</th><th data-key="exhaustion_watch">疑似衰竭</th><th data-key="distance_pct">距52周低点</th><th data-key="ret_20d_pct">20日涨跌</th><th data-key="quality_status">财务初筛</th></tr></thead><tbody id="rows"></tbody></table></div>
<p class="note">注意：高P和高R可同时出现；R不等于买盘资金流向，也不代表抛压结束。初筛质量标签不等于优质公司认证。仅显示与主交易日一致的数据。</p>
</main><script>const data=__DATA__;let sortKey="pressure_score",descending=true;
const $=id=>document.getElementById(id);
const esc=s=>String(s??"—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function meter(n,green){if(n==null)return "—";return esc(n)+'<span class="meter"><span class="fill '+(green?'green':'')+'" style="display:block;width:'+Math.max(0,Math.min(100,n))+'%"></span></span>'}
function render(){let q=$("search").value.trim().toLowerCase(),stage=$("stage").value,quality=$("quality").value;
let arr=data.filter(x=>(x.code+x.name).toLowerCase().includes(q)&&(!stage||x.repair_stage===stage)&&(!quality||x.quality_status===quality));
arr.sort((a,b)=>{let x=a[sortKey],y=b[sortKey];if(x==null)return 1;if(y==null)return -1;let c=typeof x==="number"&&typeof y==="number"?x-y:String(x).localeCompare(String(y),"zh");return descending?-c:c});
$("total").textContent=arr.length;$("ex").textContent=arr.filter(x=>x.exhaustion_watch).length;$("support").textContent=arr.filter(x=>x.repair_stage==="初步承接观察").length;
$("rows").innerHTML=arr.map(x=>'<tr><td>'+esc(x.code)+'</td><td>'+esc(x.name)+'</td><td>'+meter(x.pressure_score,false)+'</td><td>'+meter(x.repair_score,true)+'</td><td><span class="pill">'+esc(x.repair_stage)+'</span></td><td>'+(x.exhaustion_watch?"是":"否")+'</td><td>'+esc(x.distance_pct)+'%</td><td>'+esc(x.ret_20d_pct)+'%</td><td>'+esc(x.quality_status)+'</td></tr>').join("")}
["search","stage","quality"].forEach(id=>$(id).addEventListener("input",render));document.querySelectorAll("th[data-key]").forEach(el=>el.onclick=()=>{if(sortKey===el.dataset.key)descending=!descending;else{sortKey=el.dataset.key;descending=true}render()});render();</script></body></html>"""
    page=page.replace("__DAY__",html.escape(day)).replace("__DATA__",payload)
    dest=path.parent/f"dashboard_PR_{day}.html"
    dest.write_text(page,encoding="utf-8")
    print(f"Dashboard: {dest} rows={len(records)}")
if __name__=="__main__":build(sys.argv[1])
