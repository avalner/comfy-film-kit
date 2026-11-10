// Local read-only ComfyUI receiver; browser gets progress over HTTP.
const fs = require('fs'), path = require('path');
const {reduceProgress} = require('./progress.js');
const root = process.argv[2], parent = Number(process.argv[3]);
let socket, config = {}, state = {}, client;
const read = file => JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
function save() {
  const file = path.join(root,'.pipeline','progress-live.json');
  fs.writeFileSync(file+'.tmp',JSON.stringify({...state,prompt:config.prompt,connected:socket?.readyState===1,updated:Date.now()/1000}));
  fs.renameSync(file+'.tmp',file);
}
function tick() {
  try { process.kill(parent,0); } catch (_) { process.exit(0); }
  try {
    const film = read(path.join(root,'film.json'));
    const segment = film.segments.find(s=>s.status==='running') || film.segments.at(-1);
    const attempt = segment?.attempts.at(-1);
    if (!attempt) return;
    if (config.prompt !== attempt.prompt_id) state = {};
    const graph = read(path.join(root,'.pipeline','workflow-api.json'));
    config = {prompt:attempt.prompt_id,generator:film.bindings.generator,
      samplers:Object.entries(graph).filter(([id,n])=>/sampler/i.test(n.class_type)&&!/select/i.test(n.class_type)).map(([id])=>id)};
    if (segment.status==='running' && (client!==attempt.client_id || !socket || socket.readyState>1)) {
      if (socket) {socket.onclose=null;socket.close();}
      client=attempt.client_id;
      socket=new WebSocket(film.config.server.replace(/^http/,'ws')+'/ws?clientId='+encodeURIComponent(client));
      socket.onmessage=event=>{if(typeof event.data==='string'){try{state=reduceProgress(state,JSON.parse(event.data),config);save();}catch(_){}}};
      socket.onopen=save;
      socket.onerror=()=>{};
    }
    save();
  } catch (_) {}
}
tick();setInterval(tick,2000);
