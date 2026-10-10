// Synthesised sounds (Web Audio) – no audio files, works offline. Silent (never throws) if the browser blocks autoplay.
const SND={on:localStorage.mute!=='1',ctx:null};
function actx(){try{if(!SND.ctx){const A=window.AudioContext||window.webkitAudioContext;if(!A)return null;SND.ctx=new A()}if(SND.ctx.state==='suspended')SND.ctx.resume().catch(()=>{});return SND.ctx}catch(e){return null}}
document.addEventListener('click',()=>actx(),{passive:true});document.addEventListener('keydown',()=>actx(),{passive:true});
function tn(c,f,t,d,type,v){const o=c.createOscillator(),g=c.createGain();o.type=type||'sine';o.frequency.value=f;g.gain.setValueAtTime(0.0001,t);g.gain.linearRampToValueAtTime(v||.2,t+.01);g.gain.exponentialRampToValueAtTime(.0001,t+d);o.connect(g);g.connect(c.destination);o.start(t);o.stop(t+d+.05)}
function snd(n){if(!SND.on)return;try{const c=actx();if(!c||c.state!=='running')return;const t=c.currentTime;
 if(n==='bell'){[523,659,784,1046].forEach(f=>{tn(c,f,t,2.8,'sine',.16);tn(c,f*2.76,t,1.1,'sine',.04)});tn(c,523,t+.8,2.4,'sine',.1);tn(c,784,t+1.4,2,'sine',.08)}
 else if(n==='tick')tn(c,880,t,.12,'square',.1);
 else if(n==='win')[523,659,784,1046].forEach((f,i)=>tn(c,f,t+i*.11,.5,'triangle',.22));
 else if(n==='bid')tn(c,660,t,.15,'triangle',.14);
 else if(n==='warn')[0,.35,.7].forEach(d=>tn(c,440,t+d,.25,'sawtooth',.14));
 else if(n==='alert'){tn(c,330,t,.35,'sawtooth',.16);tn(c,220,t+.3,.5,'sawtooth',.16)}}catch(e){}}
function toggleSound(){SND.on=!SND.on;localStorage.mute=SND.on?'0':'1';if(SND.on){actx();snd('tick')}if(typeof render==='function')render()}
