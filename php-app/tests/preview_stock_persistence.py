"""Disposable Docker acceptance for stock persistence across container replacement.
Requires PHP_PREVIEW_TEST_ENV pointing to private test seed environment variables.
Uses only newly created containers/volumes and never targets the hosted store.
"""
from pathlib import Path
import subprocess,time,urllib.request,json,os,uuid
root=Path(__file__).resolve().parents[2];tag=uuid.uuid4().hex[:10];volume='annam-stock-test-'+tag;names=[volume+'-one',volume+'-two'];port=int(os.environ.get('PHP_PREVIEW_TEST_PORT','8158'));envfile=os.environ['PHP_PREVIEW_TEST_ENV'];test_image=os.environ.get('PHP_PREVIEW_TEST_IMAGE','annam-php-parity-final')

def run(*args):
 r=subprocess.run(args,cwd=root,capture_output=True,text=True)
 if r.returncode:raise RuntimeError('Test command failed: '+args[0]+' '+args[1])
 return r.stdout.strip()
def create(name):
 run('docker','create','--name',name,'--env-file',envfile,'-e','PREVIEW_DATA_ROOT=/var/data/annam-php-preview','-e','APP_URL=http://127.0.0.1:'+str(port),'-v',volume+':/var/data','-p','127.0.0.1:'+str(port)+':10000','--entrypoint','/bin/sh',test_image,'-c','chmod -R a+rX /opt/annam/php-app/src /opt/annam/php-app/deploy /opt/annam/config/settings; exec /opt/annam/php-app/deploy/render-start.sh')
 for source,target in [('php-app/src/.','/opt/annam/php-app/src/'),('php-app/deploy/.','/opt/annam/php-app/deploy/'),('config/settings/render_preview.py','/opt/annam/config/settings/render_preview.py')]:run('docker','cp',str(root)+'/'+source,name+':'+target)
 run('docker','start',name)
 for _ in range(100):
  try:
   if urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/healthz',timeout=2).status==200:return
  except Exception:pass
  if run('docker','inspect','--format','{{.State.Running}}',name)!='true':raise RuntimeError('Persistent test container startup failed')
  time.sleep(1)
 raise RuntimeError('Persistent test readiness timed out')
def php(name,code):
 return run('docker','exec','-e','DATABASE_DSN=sqlite:/var/data/annam-php-preview/annam.sqlite',name,'php','-r','require "/opt/annam/php-app/src/bootstrap.php";$s=new Annam\\Store(new Annam\\Database());'+code)
try:
 run('docker','volume','create',volume);create(names[0]);print('Fresh persistent preview started',flush=True)
 code='$out=[];foreach(["Rasam Vadai (1)","Rava uppuma"] as $i=>$name){$r=$s->db->one("SELECT id FROM catalog_menuitem WHERE tenant_id=? AND name=?",[$s->id(),$name]);if(!$r)throw new Exception("Missing reviewed dish");$s->setItemFlag((int)$r["id"],"in_stock",$i===0);$out[$name]=(bool)$s->item((int)$r["id"])["in_stock"];}echo json_encode($out);'
 expected=json.loads(php(names[0],code));assert list(expected.values())==[True,False]
 run('docker','stop',names[0]);run('docker','rm',names[0]);create(names[1]);print('Replaced container using same persistent database',flush=True)
 read='$out=[];foreach(["Rasam Vadai (1)","Rava uppuma"] as $name){$r=$s->db->one("SELECT in_stock FROM catalog_menuitem WHERE tenant_id=? AND name=?",[$s->id(),$name]);$out[$name]=(bool)$r["in_stock"];}echo json_encode($out);'
 assert json.loads(php(names[1],read))==expected,'Replacement reset stock values'
 php(names[1],'$s->db->rows("UPDATE catalog_menuitem SET in_stock=TRUE WHERE tenant_id=? AND name IN (?,?)",[$s->id(),"Rasam Vadai (1)","Rava uppuma"]);')
 run('docker','restart',names[1]);time.sleep(3);assert all(json.loads(php(names[1],read)).values()),'Restart lost latest updates'
 run('docker','stop',names[1])
 # A missing previously initialized database must not be recreated from defaults.
 run('docker','run','--rm','-v',volume+':/data','alpine:3.22','mv','/data/annam-php-preview/annam.sqlite','/data/annam-php-preview/saved.sqlite')
 run('docker','start',names[1]);time.sleep(3);assert run('docker','inspect','--format','{{.State.Running}}',names[1])=='false','Missing database silently reseeded'
 run('docker','run','--rm','-v',volume+':/data','alpine:3.22','mv','/data/annam-php-preview/saved.sqlite','/data/annam-php-preview/annam.sqlite')
 run('docker','rm',names[1]);print('PASS latest true/false stock survived fresh container, latest both-in-stock survived restart, missing database refused reseeding',flush=True)
finally:
 for name in names:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 subprocess.run(['docker','volume','rm',volume],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
