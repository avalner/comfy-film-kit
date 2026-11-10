import subprocess, numpy as np, json
from pathlib import Path
ff='C:/Program Files/Shotcut/ffmpeg.exe'
import argparse
ap=argparse.ArgumentParser(description='Match luminance using a verified stable background; does not inspect scene semantics.')
ap.add_argument('--input',required=True)
ap.add_argument('--output',required=True)
ap.add_argument('--ffmpeg',default=ff)
ap.add_argument('--ffprobe',default='C:/Program Files/Shotcut/ffprobe.exe')
ap.add_argument('--region',type=float,nargs=4,required=True,metavar=('X0','Y0','X1','Y1'),help='Normalized stable background rectangle, excludes subject and moving water')
ap.add_argument('--reference',type=float,nargs=2,required=True,metavar=('START','END'),help='Seconds of accepted reference lighting')
args=ap.parse_args();ff=args.ffmpeg;src=args.input;out=args.output
if Path(out).exists():ap.error('Output exists; choose a new version')
meta=json.loads(subprocess.check_output([args.ffprobe,'-v','error','-select_streams','v:0','-show_entries','stream=width,height,r_frame_rate','-of','json',src]))['streams'][0]
width,height=meta['width'],meta['height'];fps=meta['r_frame_rate'];num,den=map(float,fps.split('/'));rate=num/den
x0,y0,x1,y1=args.region
if not(0<=x0<x1<=1 and 0<=y0<y1<=1):ap.error('Invalid region')
b=subprocess.check_output([ff,'-v','error','-i',src,'-vf','scale=152:264','-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','-'])
a=np.frombuffer(b,np.uint8).reshape(-1,264,152,3).astype(np.float32)
y=a@np.array([.2126,.7152,.0722],np.float32)
qs=np.array([2,10,25,50,75,90,98])/100
cur=np.quantile(y[:,int(y0*264):int(y1*264),int(x0*152):int(x1*152)],qs,axis=(1,2)).T
# Static upper background excludes fox, leaf and moving foreground water.
# Correct luminance without independent RGB channel gains.
lo,hi=[round(t*rate) for t in args.reference]
if not(0<=lo<hi<=len(cur)):ap.error('Invalid reference range')
target=np.median(cur[lo:hi],axis=0)
luts=[]
for vals in cur:
 x=np.r_[0,vals,255]; z=np.r_[0,target,255]
 ux,idx=np.unique(x,return_index=True)
 luts.append(np.interp(np.arange(256),ux,z[idx]))
luts=np.array(luts)
# Very short smoothing removes estimation noise while tracking boundary changes.
padded=np.pad(luts,((1,1),(0,0)),mode='edge')
luts=(padded[:-2]+2*luts+padded[2:])/4
r=subprocess.Popen([ff,'-v','error','-i',src,'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE)
w=subprocess.Popen([ff,'-v','error','-n','-f','rawvideo','-pix_fmt','rgb24','-s',f'{width}x{height}','-r',fps,'-i','-','-i',src,'-map','0:v','-map','1:a?','-c:v','libx264','-pix_fmt','yuv420p','-profile:v','high','-tag:v','avc1','-crf','17','-preset','fast','-c:a','copy','-movflags','+faststart',out],stdin=subprocess.PIPE)
for lut in luts:
 raw=r.stdout.read(width*height*3)
 if len(raw)!=width*height*3:raise RuntimeError('Incomplete frame')
 fr=np.frombuffer(raw,np.uint8).reshape(height,width,3).astype(np.float32)
 lum=fr@np.array([.2126,.7152,.0722],np.float32)
 mapped=np.interp(lum,np.arange(256),lut)
 # Same offset in all channels preserves channel differences and avoids hue shifts.
 adjusted=np.clip(fr+(mapped-lum)[:,:,None],0,255).astype(np.uint8)
 w.stdin.write(adjusted.tobytes())
r.stdout.close();w.stdin.close()
if r.wait() or w.wait():raise RuntimeError('Encode failed')
subprocess.run([ff,'-v','error','-i',out,'-f','null','-'],check=True)
encoded=json.loads(subprocess.check_output([args.ffprobe,'-v','error','-select_streams','v:0','-show_entries','stream=codec_name,pix_fmt','-of','json',out]))['streams'][0]
if encoded.get('codec_name')!='h264' or encoded.get('pix_fmt')!='yuv420p':raise RuntimeError('Output is not Windows-compatible H.264 yuv420p')
Path(out+'.lighting.json').write_text(json.dumps({'reference_frames':[lo,hi],'region':args.region,'quantiles':qs.tolist(),'target':target.tolist(),'frames':len(luts),'method':'luminance quantile matching; equal RGB offsets; 3-frame smoothing'},indent=2))
print(json.dumps({'file':out,'frames':len(luts),'decode':'passed'}))

