import json
from django.core.management.base import BaseCommand,CommandError
from apps.operations.backups import create_backup,upload_supabase_backup


class Command(BaseCommand):
    help='Create an encrypted PostgreSQL, media, private-bill and recovery-key backup.'
    def add_arguments(self,parser):
        parser.add_argument('--output',required=True)
        parser.add_argument('--upload',action='store_true')
    def handle(self,*args,**options):
        try:
            result=create_backup(options['output'])
            if options['upload']:result.update(upload_supabase_backup(options['output']))
        except (ValueError,OSError) as exc:raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result))
