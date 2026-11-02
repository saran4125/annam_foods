import json,os,shutil
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from apps.operations.backups import encryption_key


class Command(BaseCommand):
    help='Report operational gaps without exposing passwords, customer data or recovery keys.'
    def add_arguments(self,parser):parser.add_argument('--strict',action='store_true')
    def handle(self,*args,**options):
        checks={
            'debug_disabled':not settings.DEBUG,
            'secure_sessions':bool(getattr(settings,'SESSION_COOKIE_SECURE',False)),
            'https_redirect':bool(getattr(settings,'SECURE_SSL_REDIRECT',False)),
            'database_tls_required':settings.DATABASES['default'].get('OPTIONS',{}).get('sslmode') in ('require','verify-ca','verify-full'),
            'offsite_backup_settings_present':all(os.environ.get(k) for k in ['BACKUP_SUPABASE_URL','BACKUP_SUPABASE_BUCKET','BACKUP_SUPABASE_TOKEN']),
            'durable_storage_declared':bool(getattr(settings,'STORAGE_PERSISTENT',False)),
            'worker_readiness_required':bool(getattr(settings,'REQUIRE_WORKER_HEARTBEAT',False)),
            'postgres_backup_client':bool(shutil.which(os.environ.get('PG_DUMP_BIN','pg_dump'))),
        }
        try:encryption_key();checks['separate_backup_key_configured']=True
        except ValueError:checks['separate_backup_key_configured']=False
        self.stdout.write(json.dumps({'checks':checks,'external_verification_required':[
            'Off-site encrypted backup schedule and retention','Restore drill using a production backup in an isolated environment',
            'Storage survives a real redeploy','Hosting alert delivery and production load test']},indent=2))
        if options['strict'] and not all(checks.values()):raise CommandError('Operational requirements are incomplete. Review the failed checks.')
