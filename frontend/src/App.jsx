import React,{useEffect,useState} from 'react'
import {createRoot} from 'react-dom/client'
import './style.css'

const signals=['A','B','C','D']
const colors={car:'#a3c4e7',motorcycle:'#f4d179',bus:'#f78465',auto:'#84dba7',truck:'#c7afd9'}
function Road({frame:target,select,heat}){
  const prior=React.useRef(null)
  const [frame,show]=useState(target)
  useEffect(()=>{
    const received=performance.now()
    const last=prior.current
    prior.current={data:target,received}
    if(!last || target.time!==last.data.time+1 || received-last.received>1000){
      show(target)
      return
    }
    const duration=Math.max(16,received-last.received)
    const endpoints=new Map(target.vehicles.map(v=>[v.id,v]))
    let request
    function draw(now){
      const t=Math.min(1,(now-received)/duration)
      if(t>=1){show(target);return}
      const vehicles=last.data.vehicles.map(v=>{
        const end=endpoints.get(v.id)
        if(!end)return v
        const turn=(end.angle-v.angle+540)%360-180
        return {...v,x:v.x+(end.x-v.x)*t,y:v.y+(end.y-v.y)*t,angle:v.angle+turn*t}
      })
      show({...last.data,vehicles})
      request=requestAnimationFrame(draw)
    }
    request=requestAnimationFrame(draw)
    return ()=>cancelAnimationFrame(request)
  },[target])
  const junctions=Object.entries(frame.junctions)
  const s=frame.signals
  return <svg viewBox="-20 -25 1540 350" aria-label="Live SUMO road network">
    <defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#35504d"/></pattern></defs>
    <rect x="-20" y="-25" width="1540" height="350" fill="url(#grid)"/>
    <path d="M0 150H1500" className="road"/>
    {junctions.map(([id,[x]])=><g key={id}><path d={`M${x} 0V300`} className="road"/><path d={`M${x} 0V300`} className="stripe"/></g>)}
    <path d="M0 150H1500" className="stripe"/>
    {junctions.map(([id,[x]])=><g key={id} onClick={()=>select(id)} style={{cursor:'pointer'}}>
      {heat&&<circle cx={x} cy="150" r="38" fill={s[id].queue[0]+s[id].queue[1]>10?'#fa8247':'#71d9a3'} opacity=".24"/>}
      <rect x={x+16} y="76" width="88" height="35" rx="7" fill="#152927" stroke="#47625b"/><text x={x+28} y="100" fill="#dceedf" fontSize="21">SIG {id}</text>
      {[0,1].map(k=><circle key={k} cx={x+(k?12:-17)} cy={150+(k?-18:12)} r="4" fill={s[id].axis===k&&s[id].stage!=='clear'?(s[id].stage==='green'?'#88ffa9':'#ffd591'):'#ed6962'}/>)}</g>)}
    {frame.predictions.filter(p=>frame.mode==='cascaded' && frame.signals[p.destination].incoming.some(i=>i.source===p.source) && frame.signals[p.destination].axis===0 && frame.signals[p.destination].stage==='green' && p.arrival<=frame.signals[p.destination].green_end).map(p=><path key={p.members[0]} d={`M${frame.junctions[p.source][0]} 168H${frame.junctions[p.destination][0]}`} className="wave"/>)}
    {frame.vehicles.map(v=><rect key={v.id} style={{transform:`translate(${v.x}px,${300-v.y}px) rotate(${v.angle}deg)`}} x="-1.4" y="-3" rx="1" width={v.kind==='motorcycle'?1.5:2.8} height={v.kind==='bus'||v.kind==='truck'?11:5} fill={colors[v.kind]}/>)}
  </svg>
}
function App(){
 const [frame,F]=useState(null),[online,O]=useState(false),[id,I]=useState('A'),[heat,H]=useState(false),[paused,P]=useState(false),[action,A]=useState('normal'),[error,E]=useState(''),[history,T]=useState([])
 useEffect(()=>{const es=new EventSource('/events');es.onmessage=e=>{const f=JSON.parse(e.data);F(f);O(true);T(old=>[...old.slice(-89),{count:f.vehicles.length,...f.metrics,green:f.signals.A.approved}])};es.onerror=()=>O(false);return()=>es.close()},[])
 async function control(a,p,target=id){try{const res=await fetch('/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a,paused:p,target})});if(!res.ok)throw Error();A(a);P(p);E('')}catch{E('Control update failed')}}
 const [metric,M]=useState('count')
 const [comparison,C]=useState([])
 useEffect(()=>{fetch('/comparison').then(r=>r.ok?r.json():[]).then(C).catch(()=>C([]))},[])
 const obs=frame?.signals[id]
 return <main><header><b className="brand">GreenWave <em>AI</em></b><span>{online?'● Connected':'○ Connecting'} · Bengaluru</span></header>
 <h1>Corridor operations</h1><p>Four-intersection traffic simulation</p>
 {!frame?<section>Waiting for the local SUMO service…</section>:<>
 <div className="stats">{Object.entries({'Active vehicles':frame.vehicles.length,'Entered network':frame.entered,'Completed trips':frame.completed,'Simulation time':frame.time+' s'}).map(([k,v])=><section key={k}><small>{k}</small><strong>{v}</strong></section>)}</div>
 <section><div className="row"><h2>Live corridor</h2><button onClick={()=>H(!heat)}>Heatmap {heat?'on':'off'}</button></div><Road frame={frame} select={I} heat={heat}/><div className="legend">{Object.entries(colors).map(([k,c])=><span key={k} style={{color:c}}>● {k}</span>)}</div></section>
 <div className="columns"><section><div className="row"><h2>Decision inspector</h2><select value={id} onChange={e=>I(e.target.value)}>{signals.map(s=><option key={s} value={s}>Signal {s}</option>)}</select></div>
 {Object.entries({'Executed phase':(obs.axis?'North–south':'East–west')+' / '+obs.stage,'Phase elapsed':obs.elapsed+' s','Committed minimum remaining':obs.minimum_remaining+' s','Predicted green end':obs.green_end==null?'Clearance':obs.green_end+' s','Decision basis':obs.reason,'Fairness intervention':obs.fairness?'Active':'Clear','Recommended green':obs.recommended+' s','Approved green plan':obs.approved+' s','Queues · EW / NS':obs.queue.join(' / '),'Longest waits · EW / NS':obs.wait.join(' / ')+' s','Receiving service estimate':obs.capacity.toFixed(2)+' veh/s'}).map(([k,v])=><div className="line" key={k}><span>{k}</span><b>{v}</b></div>)}</section>
 <section><h2>Simulation controls</h2><label>Demand and communication<select value={action} onChange={e=>control(e.target.value,paused)}>{Object.entries({normal:'Normal operation',corridor:'Increase corridor arrivals',cross:'Increase selected cross-road arrivals',reduce:'Reduce arrivals',slow:'Reduce approach speeds',block:'Block selected north approach lane',offline:'Disconnect signal communications'}).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><button onClick={()=>control(action,!paused)}>{paused?'Resume':'Pause'}</button> {error}<h2>Metric history</h2><select aria-label="History metric" value={metric} onChange={e=>M(e.target.value)}>{Object.entries({count:'Active vehicles',speed:'Mean speed (m/s)',wait:'Mean current wait (s)',queue:'Queued vehicles',density:'Vehicle density (veh/lane-km)',green:'Signal A green plan (s)',throughput:'Exits in last minute',entered_min:'Entries in last minute'}).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select><svg viewBox="0 0 180 44"><polyline fill="none" stroke="#84dba7" points={history.map((n,i)=>[i*2,43-40*(n[metric]||0)/Math.max(1,...history.map(row=>row[metric]||0))].join(',')).join(' ')}/></svg></section></div>
 <section><h2>Arrivals at Signal {id}</h2>{obs.incoming.length?obs.incoming.map(p=><div className="line" key={p.members[0]}><b>{p.source} → {p.destination}</b><span>{p.count} vehicles · arrival window {p.window.join('–')} s</span></div>):<p>No current arrival prediction.</p>}</section>
 <section><h2>Signal communications</h2>{(frame.messages||[]).filter(m=>m.destination===id).map(m=><details key={m.version}><summary>{m.source} ? {id} ? {m.kind} ? issued {m.time} s</summary><pre>{JSON.stringify(m.data,null,2)}</pre></details>)}</section>
 <section><h2>Camera monitoring</h2><p>{frame.cameraStatus}</p>{Object.entries(frame.cameras||{}).map(([s,c])=><figure key={s}><img width="240" src={'data:image/jpeg;base64,'+c.image} alt={'Rendered camera '+s}/><figcaption>Signal {s} ? {c.time} s ? {c.stage} ? {c.detector} ? {c.tracks.length} tracks ? {c.latency_ms} ms ? precision {c.precision?.toFixed(2)??"?"} ? recall {c.recall?.toFixed(2)??"?"}</figcaption></figure>)}</section>
 <section><h2>Controller comparison</h2>{comparison.length?<div style={{overflowX:'auto'}}><p>Seed {comparison[0].seed} ? {comparison[0].seconds} simulated seconds</p><table><thead><tr>{['Controller','Completed trips','Mean trip (s)','Stops','Mean EW queue','Mean NS queue'].map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{comparison.map(r=><tr key={r.mode}>{['mode','completed','mean_trip_seconds','stops','mean_corridor_queue','mean_cross_queue'].map(k=><td key={k}>{k==='mode'?r[k]:Number(r[k]).toLocaleString(undefined,{maximumFractionDigits:1})}</td>)}</tr>)}</tbody></table></div>:<p>No recorded comparison available.</p>}</section>
 <section><h2>Signal transitions</h2>{frame.events.slice(-6).reverse().map(e=><div className="line" key={e.time+e.signal}><span>{e.time} s · Signal {e.signal}</span><b>{e.stage}</b></div>)}</section></>}</main>
}
createRoot(document.getElementById('root')).render(<App/>)
