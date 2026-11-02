from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.operations.models import RateLimitBucket


class Command(BaseCommand):
    help='Delete only expired rate-limit windows; never touches customer/order history.'
    def handle(self,*args,**options):
        count,_=RateLimitBucket.all_tenants.filter(expires_at__lt=timezone.now()).delete()
        self.stdout.write(f'Removed {count} expired operational windows.')
