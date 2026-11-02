"""Encrypted, authenticated database/media snapshots. Recovery keys never go in logs."""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from django.conf import settings

MAGIC=b'ANNAM-BACKUP-1\n'
CHUNK=1024*1024


def encryption_key():
    try:
        key=base64.b64decode(os.environ['BACKUP_ENCRYPTION_KEY'],altchars=b'-_',validate=True)
        if len(key)!=32:raise ValueError()
        return key
    except (KeyError,ValueError) as exc:
        raise ValueError('Set BACKUP_ENCRYPTION_KEY to a separate base64-encoded 32-byte key.') from exc


def private_destination(path):
    path=Path(path).resolve()
    roots=[Path(settings.MEDIA_ROOT).resolve(),Path(settings.STATIC_ROOT).resolve(),Path(getattr(settings,'PRIVATE_BILLS_ROOT',settings.BASE_DIR/'private-bills')).resolve()]
    roots.extend(Path(p).resolve() for p in settings.STATICFILES_DIRS)
    if any(path==root or root in path.parents for root in roots):
        raise ValueError('Backups and recovery files must stay outside public media/static directories.')
    return path


def database_environment():
    config=settings.DATABASES['default']
    if config['ENGINE']!='django.db.backends.postgresql':raise ValueError('Use PostgreSQL for production database backups.')
    env=os.environ.copy()
    env.update(PGHOST=str(config.get('HOST') or '127.0.0.1'),PGPORT=str(config.get('PORT') or '5432'),
               PGUSER=str(config['USER']),PGPASSWORD=str(config['PASSWORD']),PGDATABASE=str(config['NAME']),PGCONNECT_TIMEOUT='10')
    env['PGSSLMODE']=config.get('OPTIONS',{}).get('sslmode','prefer')
    return env


def encrypt_file(source,destination,key):
    nonce=os.urandom(12);encryptor=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(MAGIC)
    destination.write(MAGIC+nonce)
    while block:=source.read(CHUNK):destination.write(encryptor.update(block))
    destination.write(encryptor.finalize());destination.write(encryptor.tag)


def decrypt_file(source,destination,key):
    size=source.seek(0,2);source.seek(0)
    if source.read(len(MAGIC))!=MAGIC or size<len(MAGIC)+28:raise ValueError('Not a supported encrypted backup.')
    nonce=source.read(12);source.seek(-16,2);tag=source.read(16);source.seek(len(MAGIC)+12)
    decryptor=Cipher(algorithms.AES(key),modes.GCM(nonce,tag)).decryptor();decryptor.authenticate_additional_data(MAGIC)
    remaining=size-len(MAGIC)-28
    while remaining:
        block=source.read(min(CHUNK,remaining))
        if not block:raise ValueError('Truncated backup.')
        remaining-=len(block);destination.write(decryptor.update(block))
    destination.write(decryptor.finalize())


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        while block:=source.read(CHUNK):digest.update(block)
    return digest.hexdigest()


def create_backup(output):
    key=encryption_key();output=private_destination(output)
    if output.exists():raise ValueError('Choose a new backup filename; existing backups are never overwritten.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='annam-backup-') as directory:
        staging=Path(directory);dump=staging/'database.dump'
        try:
            subprocess.run([os.environ.get('PG_DUMP_BIN','pg_dump'),'--format=custom','--no-owner','--no-acl','--file',str(dump)],
                           env=database_environment(),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=600)
        except (OSError,subprocess.SubprocessError) as exc:
            raise ValueError('PostgreSQL backup failed. Check connectivity and install a matching pg_dump client.') from exc
        recovery=staging/'recovery.json'
        recovery.write_text(json.dumps({'SECRET_KEY':settings.SECRET_KEY,'SECRETS_KEY':getattr(settings,'SECRETS_KEY','')}))
        os.chmod(recovery,0o600)
        files=[('meta/database.dump',dump),('meta/recovery.json',recovery)]
        for namespace,root in [('public-media',settings.MEDIA_ROOT),('private-bills',getattr(settings,'PRIVATE_BILLS_ROOT',settings.BASE_DIR/'private-bills'))]:
            root=Path(root)
            if not root.is_dir():continue
            for base,dirs,names in os.walk(root,followlinks=False):
                dirs[:]=sorted(d for d in dirs if not (Path(base)/d).is_symlink())
                for name in sorted(names):
                    path=Path(base)/name
                    if path.is_file() and not path.is_symlink():files.append((namespace+'/'+path.relative_to(root).as_posix(),path))
        manifest={'format':1,'created_at':datetime.now(timezone.utc).isoformat(),
                  'files':{name:{'sha256':sha256(path),'size':path.stat().st_size} for name,path in files}}
        archive=staging/'archive.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            for name,path in files:tar.add(path,arcname=name,recursive=False)
            manifest_path=staging/'manifest.json';manifest_path.write_text(json.dumps(manifest))
            tar.add(manifest_path,arcname='meta/manifest.json',recursive=False)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent,prefix='.backup-',delete=False) as target:
                temporary=Path(target.name)
                with archive.open('rb') as source:encrypt_file(source,target,key)
                target.flush();os.fsync(target.fileno())
            verify_backup(temporary)
            os.link(temporary,output)  # atomic, refuses an existing destination
        finally:
            if temporary:temporary.unlink(missing_ok=True)
    return {'files':len(files),'bytes':output.stat().st_size}


def verify_backup(backup,extract_to=None):
    key=encryption_key()
    if extract_to:
        extract_to=private_destination(extract_to)
        if extract_to.exists() and any(extract_to.iterdir()):raise ValueError('Recovery directory must be empty.')
    with tempfile.TemporaryDirectory(prefix='annam-verify-') as directory:
        plain=Path(directory)/'archive.tar.gz'
        try:
            with Path(backup).open('rb') as source,plain.open('wb') as target:decrypt_file(source,target,key)
        except Exception as exc:raise ValueError('Backup authentication failed; wrong key, corrupt or incomplete backup.') from exc
        with tarfile.open(plain,'r:gz') as archive:
            members={}
            total=0
            for member in archive:
                name=PurePosixPath(member.name)
                if (not member.isfile() or not name.parts or name.is_absolute() or '..' in name.parts or '\\' in member.name or
                    name.parts[0] not in ('meta','public-media','private-bills') or member.name in members):
                    raise ValueError('Unsafe archive member.')
                total+=member.size
                if len(members)>100000 or total>int(os.environ.get('BACKUP_VERIFY_MAX_BYTES',str(20*1024**3))):raise ValueError('Backup exceeds recovery limits.')
                members[member.name]=member
            if not {'meta/manifest.json','meta/database.dump','meta/recovery.json'}.issubset(members):raise ValueError('Backup is missing required recovery files.')
            manifest=json.load(archive.extractfile(members['meta/manifest.json']))
            if set(manifest['files'])!=set(members)-{'meta/manifest.json'}:raise ValueError('Backup manifest does not match contents.')
            for name,expected in manifest['files'].items():
                digest=hashlib.sha256();size=0
                with archive.extractfile(members[name]) as source:
                    while block:=source.read(CHUNK):digest.update(block);size+=len(block)
                if digest.hexdigest()!=expected['sha256'] or size!=expected['size']:raise ValueError('Backup file checksum mismatch.')
            if extract_to:
                extract_to.mkdir(parents=True,exist_ok=True,mode=0o700)
                for name,member in members.items():
                    destination=extract_to/name;destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    with archive.extractfile(member) as source,destination.open('xb') as target:shutil.copyfileobj(source,target,CHUNK)
                    os.chmod(destination,0o600)
    return {'files':len(manifest['files']),'created_at':manifest['created_at']}


def upload_supabase_backup(backup):
    """Stream encrypted bytes to an operator-configured private Supabase bucket."""
    import http.client
    from urllib.parse import urlsplit,quote
    parsed=urlsplit(os.environ.get('BACKUP_SUPABASE_URL',''))
    bucket=os.environ.get('BACKUP_SUPABASE_BUCKET','')
    token=os.environ.get('BACKUP_SUPABASE_TOKEN','')
    if parsed.scheme!='https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or not bucket or not token or '\r' in token or '\n' in token:
        raise ValueError('Configure the HTTPS Supabase URL, private backup bucket and backend-only upload token.')
    path=Path(backup)
    # Re-authenticate locally before any external upload.
    verify_backup(path)
    endpoint=parsed.path.rstrip('/')+'/storage/v1/object/'+quote(bucket,safe='')+'/'+quote(path.name,safe='')
    connection=http.client.HTTPSConnection(parsed.hostname,parsed.port or 443,timeout=60)
    try:
        connection.putrequest('POST',endpoint)
        connection.putheader('Authorization','Bearer '+token)
        connection.putheader('Content-Type','application/octet-stream')
        connection.putheader('Content-Length',str(path.stat().st_size))
        connection.putheader('x-upsert','false')
        connection.endheaders()
        with path.open('rb') as source:
            while block:=source.read(CHUNK):connection.send(block)
        response=connection.getresponse()
        response.read(4096)
        if not 200<=response.status<300:raise ValueError('Backup upload was not confirmed; local encrypted copy retained.')
    except (OSError,http.client.HTTPException) as exc:
        raise ValueError('Backup upload failed; local encrypted copy retained. Check the private bucket and credentials.') from exc
    finally:connection.close()
    return {'upload_confirmed':True,'object':path.name}
