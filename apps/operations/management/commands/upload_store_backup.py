import json
from django.core.management.base import BaseCommand,CommandError
from apps.operations.backups import upload_supabase_backup


class Command(BaseCommand):
    help='Retry upload of an already encrypted, verified backup without overwriting it locally.'
    def add_arguments(self,parser):parser.add_argument('backup')
    def handle(self,*args,**options):
        try:result=upload_supabase_backup(options['backup'])
        except (ValueError,OSError) as exc:raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result))
