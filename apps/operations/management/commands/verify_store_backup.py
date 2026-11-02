import json
from django.core.management.base import BaseCommand,CommandError
from apps.operations.backups import verify_backup


class Command(BaseCommand):
    help='Authenticate every backup file; optionally extract to an empty PRIVATE recovery folder. Does not overwrite any database.'
    def add_arguments(self,parser):
        parser.add_argument('backup')
        parser.add_argument('--extract-to')
    def handle(self,*args,**options):
        try:result=verify_backup(options['backup'],options['extract_to'])
        except (ValueError,OSError,KeyError) as exc:raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result))
