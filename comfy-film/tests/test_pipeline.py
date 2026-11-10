import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import socket
import subprocess
import sys
from unittest.mock import patch
import unittest
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

TOOLKIT = Path(__file__).resolve().parents[1]
SCRIPTS = TOOLKIT / 'scripts'
BASE = Path.cwd()
(BASE/'work/comfy-film-tests').mkdir(parents=True,exist_ok=True)
spec = importlib.util.spec_from_file_location('film', SCRIPTS / 'film.py')
film = importlib.util.module_from_spec(spec)
spec.loader.exec_module(film)
CFG = film.defaults()


class FakeComfy(BaseHTTPRequestHandler):
    graphs = {}
    completed = False
    video = b''
    uploads = 0
    fail_response = False

    def log_message(self, *args): pass

    def response(self, value):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(value).encode())

    def do_GET(self):
        if self.path == '/queue':
            self.response({'queue_running': [], 'queue_pending': []})
        elif self.path.startswith('/view?'):
            self.send_response(200);self.end_headers();self.wfile.write(self.video)
        elif self.path.startswith('/history'):
            entries = {}
            for pid,g in self.graphs.items():
                entries[pid] = {'prompt':[0,pid,g], 'status':{'completed':self.completed,'status_str':'success','messages':[]},
                                'outputs':{'92':{'images':[{'filename':'test.mp4','subfolder':'video','type':'output'}]}}}
            if '?' not in self.path:
                pid = self.path.rsplit('/',1)[-1]
                entries = {pid:entries[pid]} if pid in entries and self.completed else {}
            self.response(entries)
        else: self.response({})

    def do_POST(self):
        data = self.rfile.read(int(self.headers['Content-Length']))
        if self.path == '/upload/image':
            FakeComfy.uploads += 1
            self.response({'name':str(self.uploads)+'.png','subfolder':'test','type':'input'})
        elif self.path == '/prompt':
            pid = str(len(self.graphs)+1)
            self.graphs[pid] = json.loads(data)['prompt']
            if self.fail_response:
                self.connection.close()
                return
            self.response({'prompt_id':pid,'node_errors':{}})


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=BASE/'work/comfy-film-tests')
        cls.root = Path(cls.tmp.name)
        cls.video1 = cls.root/'source with space.mp4'
        cls.video2 = cls.root/'silent.mp4'
        film.run_process([CFG['ffmpeg'],'-v','error','-f','lavfi','-i','testsrc2=size=160x288:rate=24',
                          '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1.5','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',cls.video1])
        film.run_process([CFG['ffmpeg'],'-v','error','-f','lavfi','-i','testsrc2=size=128x128:rate=24','-t','1.5','-c:v','libx264',cls.video2])
        from PIL import Image
        cls.image = cls.root/'square.png'; Image.new('RGB',(333,333),'orange').save(cls.image)
        cls.prompt = cls.root/'prompt.txt'; cls.prompt.write_text('A continuous shot.',encoding='utf-8')
        FakeComfy.video=cls.video1.read_bytes()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),FakeComfy)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.tmp.cleanup()

    def project(self,name):
        root=self.root/name
        film.main(['init','--project',str(root),'--width','160','--height','288','--server',f'http://127.0.0.1:{self.server.server_port}'])
        return root

    def invoke(self,command,root,*args):
        return film.main([command,'--project',str(root),*map(str,args)])

    def test_approval_gates_and_continue(self):
        root=self.project('gates')
        self.invoke('import',root,'--file',self.video1)
        with self.assertRaises(film.FilmError):self.invoke('add',root,'--prompt-file',self.prompt)
        with self.assertRaises(film.FilmError):self.invoke('stitch',root)
        self.invoke('accept',root)
        with self.assertRaises(film.FilmError):self.invoke('accept',root)
        r=self.invoke('add',root,'--prompt-file',self.prompt,'--seconds','15','--loop')
        self.assertTrue(Path(r['first_frame']).exists())
        p=film.read(root/'film.json');self.assertEqual(len(p['segments']),2)
        from PIL import Image
        im=Image.open(root/p['segments'][1]['first']);self.assertEqual(im.size,(320,576));im.close()

    def test_submission_wait_and_resume(self):
        FakeComfy.completed=False;FakeComfy.fail_response=False
        root=self.project('submit')
        self.invoke('add',root,'--first',self.image,'--last',self.image,'--prompt-file',self.prompt,'--seconds',15)
        result=self.invoke('run',root,'--seed',7)
        self.assertEqual(result['frames'],362)
        graph=FakeComfy.graphs[result['prompt_id']]
        self.assertEqual(graph['105:104']['inputs']['width'],160)
        self.assertNotIn('119',graph)
        from PIL import Image
        for name in ['first','last']:
            with Image.open(root/f'.pipeline/segments/0001/{name}-canvas.png') as im:self.assertEqual(im.size,(160,288))
        with self.assertRaises(film.FilmError):self.invoke('run',root)
        timed=self.invoke('wait',root,'--timeout',.01,'--poll',.01)
        self.assertEqual(timed['status'],'still_running')
        FakeComfy.completed=True
        done=self.invoke('wait',root,'--timeout',1,'--poll',.01)
        self.assertEqual(done['status'],'review');self.assertTrue(Path(done['review']).exists())
        self.invoke('accept',root)
        self.assertEqual(self.invoke('status',root)['segments'][0]['status'],'accepted')

    def test_three_clips_all_join_modes_and_missing_audio(self):
        root=self.project('three clips')
        for source in [self.video1,self.video2,self.video1]:
            self.invoke('import',root,'--file',source);self.invoke('accept',root)
        self.invoke('trim',root,'--segment',1,'--tail',.25)
        self.invoke('join',root,'--after',1,'--mode','crossfade','--seconds',.25)
        self.invoke('join',root,'--after',2,'--mode','optical','--seconds',.25)
        result=self.invoke('stitch',root)
        self.assertEqual(result['segments'],3)
        self.assertTrue(result['media']['audio'])
        self.assertEqual(result['media']['frames'],90) # 108 original - 6 trim - 12 overlap
        self.assertLess(abs(result['media']['duration']-3.75),.1)
        with self.assertRaises(film.FilmError):self.invoke('stitch',root,'--output',result['file'])

    def test_many_segments_default_cut(self):
        root=self.project('many')
        for _ in range(7):
            self.invoke('import',root,'--file',self.video2);self.invoke('accept',root)
        result=self.invoke('stitch',root)
        self.assertEqual(result['media']['frames'],252)
        self.assertLess(abs(result['media']['duration']-10.5),.2)

    def test_lock_and_validation(self):
        root=self.project('lock')
        with film.project_lock(root):
            with self.assertRaises(film.FilmError):self.invoke('status',root)
            with self.assertRaises(film.FilmError):self.invoke('unlock',root)
        self.assertFalse((root/'.pipeline/lock').exists())
        with self.assertRaises(film.FilmError):self.invoke('add',root,'--first',self.image,'--prompt-file',self.prompt,'--seconds',16)

    def test_uncertain_submission_recovery_no_duplicate(self):
        FakeComfy.completed=False;FakeComfy.fail_response=True
        root=self.project('recover')
        self.invoke('add',root,'--first',self.image,'--last',self.image,'--prompt-file',self.prompt)
        count=len(FakeComfy.graphs)
        try:
            with self.assertRaises(Exception): self.invoke('run',root)
        finally:FakeComfy.fail_response=False
        self.assertEqual(len(FakeComfy.graphs),count+1)
        self.assertEqual(self.invoke('status',root)['segments'][0]['status'],'submitting')
        recovered=self.invoke('recover',root)
        self.assertEqual(recovered['status'],'running')
        self.assertEqual(len(FakeComfy.graphs),count+1)

    def test_inspect_and_rejected_candidate(self):
        root=self.project('inspection')
        self.invoke('import',root,'--file',self.video1)
        result=self.invoke('inspect',root)
        self.assertTrue(all(Path(x).exists() for x in result['previews'].values()))
        self.invoke('reject',root,'--reason','test rejection')
        with self.assertRaises(film.FilmError):self.invoke('accept',root)
        with self.assertRaises(film.FilmError):self.invoke('stitch',root)



    def test_project_preferences_applied_to_workflow(self):
        FakeComfy.completed=False;FakeComfy.fail_response=False
        root=self.root/'preferences'
        film.main(['init','--project',str(root),'--width','160','--height','288',
                   '--server',f'http://127.0.0.1:{self.server.server_port}',
                   '--quality','standard','--audio','silent','--music','later','--seconds','15'])
        self.invoke('add',root,'--first',self.image,'--last',self.image,'--prompt-file',self.prompt)
        r=self.invoke('run',root)
        g=FakeComfy.graphs[r['prompt_id']]
        self.assertEqual(r['frames'],362)
        self.assertFalse(g['105:126']['inputs']['value'])
        self.assertNotIn('audio',g['105:91']['inputs'])
        self.assertNotIn('105:23',g)
        self.assertEqual(self.invoke('status',root)['config']['music'],'later')

    def test_autostart_local_helper_and_no_duplicate(self):
        folder=self.root/'startup';folder.mkdir()
        helper=folder/'server.py'
        helper.write_text('''import json,sys
from http.server import HTTPServer,BaseHTTPRequestHandler
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'queue_running':[],'queue_pending':[]}).encode())
HTTPServer(('127.0.0.1',int(sys.argv[1])),Handler).serve_forever()
''')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        config={'server':f'http://127.0.0.1:{port}', 'startup':{'enabled':True,'argv':[sys.executable,str(helper),str(port)],'cwd':str(folder),'log_dir':str(folder/'logs'),'timeout':15}}
        spawned=[];real=subprocess.Popen
        def launch(*a,**kw):
            if sys.platform=='win32':self.assertTrue(kw['creationflags'] & subprocess.CREATE_NO_WINDOW)
            proc=real(*a,**kw);spawned.append(proc);return proc
        try:
            with patch.object(film.subprocess,'Popen',side_effect=launch):
                first=film.ensure_server(config);second=film.ensure_server(config)
            self.assertEqual(first['status'],'started');self.assertEqual(second['status'],'already_running')
            self.assertEqual(len(spawned),1)
            self.assertFalse((folder/'logs/startup.lock').exists())
        finally:
            for proc in spawned:
                proc.terminate();proc.wait(timeout=5)

    def test_autostart_disabled_remote_and_failed_launch(self):
        config={'server':'http://127.0.0.1:1','startup':{'enabled':False}}
        with patch.object(film,'server_ready',return_value=False):
            with self.assertRaises(film.FilmError):film.ensure_server(config)
            remote={'server':'http://192.0.2.1:8188','startup':{'enabled':True}}
            with self.assertRaises(film.FilmError):film.ensure_server(remote)
            folder=self.root/'failed-start';folder.mkdir()
            config['startup']={'enabled':True,'argv':[sys.executable,'-c','raise SystemExit(7)'], 'cwd':str(folder),'log_dir':str(folder/'logs'),'timeout':10}
            with self.assertRaisesRegex(film.FilmError,'exited with code 7'):film.ensure_server(config)
            self.assertFalse((folder/'logs/startup.lock').exists())

if __name__=='__main__': unittest.main(verbosity=2)
