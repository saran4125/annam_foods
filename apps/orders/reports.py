"""Live, tenant-scoped reports from immutable order and payment snapshots."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from django.utils import timezone
from .models import Order, CourierCharge


def report_data(*, start, end, meal='', product='', delivery_date=None, include_cancelled=False):
    if timezone.is_naive(start) or timezone.is_naive(end) or end <= start:
        raise ValueError('Choose a valid start and end date/time; end must be later than start.')
    qs=Order.objects.filter(placed_at__gte=start,placed_at__lt=end).select_related('slot').exclude(online_payment__mode='test')
    if not include_cancelled:
        qs=qs.exclude(status='cancelled')
    if delivery_date:
        qs=qs.filter(delivery_date=delivery_date)
    products=defaultdict(lambda:{'quantity':0,'amount':Decimal('0'),'orders':set()})
    order_total=paid_order_value=Decimal('0');count=0
    for order in qs.iterator():
        selected=False
        for line in order.items:
            category=line.get('meal_key') or (order.slot.key if order.slot_id else 'snacks' if order.fulfilment=='courier' else 'unclassified')
            if meal and category!=meal:
                continue
            if product and product.casefold() not in str(line.get('name','')).casefold() and product!=str(line.get('item_id','')):
                continue
            key=(category,str(line.get('item_id','')),line.get('name',''),line.get('category_name',''))
            row=products[key];row['quantity']+=int(line['quantity']);row['amount']+=Decimal(str(line['line_total']));row['orders'].add(order.pk);selected=True
        if selected:
            count+=1;order_total+=order.total
            if order.payment_status=='paid':paid_order_value+=order.total
    rows=[{'meal':key[0],'product_id':key[1],'product':key[2],'catalog_category':key[3],
           'quantity':value['quantity'],'amount':value['amount'],'orders':len(value['orders'])} for key,value in sorted(products.items())]
    return {'rows':rows,'order_count':count,'order_value':order_total,'paid_order_value':paid_order_value,
            'quantity':sum(r['quantity'] for r in rows),'items_amount':sum((r['amount'] for r in rows),Decimal('0'))}


def daily_sales():
    from .models import OrderEvent
    now=timezone.localtime();start=timezone.make_aware(datetime.combine(now.date(),time.min),now.tzinfo);end=now
    orders=Order.objects.filter(placed_at__gte=start,placed_at__lte=end).exclude(status='cancelled').exclude(online_payment__mode='test')
    gross=sum((o.total for o in orders),Decimal('0'))
    # Receipt events record collection date; a payment for yesterday's order received
    # today belongs to today's receipts, not yesterday's sales order count.
    paid_ids=OrderEvent.objects.filter(at__gte=start,at__lte=end,note__startswith='Payment receipt confirmed.').values_list('order_id',flat=True).distinct()
    manual=Order.objects.filter(pk__in=paid_ids).exclude(online_payment__mode='test')
    collected=sum((o.total for o in manual),Decimal('0'))
    from apps.payments.models import PaymentIntent, Refund
    online_collected=sum((Decimal(p.amount)/100 for p in PaymentIntent.objects.filter(mode='live',captured_at__gte=start,captured_at__lte=end)),Decimal('0'))
    refunds=sum((Decimal(r.amount)/100 for r in Refund.objects.filter(intent__mode='live',state='processed',processed_at__gte=start,processed_at__lte=end)),Decimal('0'))
    paid_today=sum((o.total for o in orders if o.payment_status=='paid'),Decimal('0'))
    courier=sum((c.amount for c in CourierCharge.objects.filter(paid_at__gte=start,paid_at__lte=end) if c.amount is not None),Decimal('0'))
    return {'as_of':now,'order_count':orders.count(),'order_value':gross,'paid_order_value':paid_today,
            'online_receipts':online_collected,'refunds':refunds,'net_receipts':collected+online_collected+courier-refunds,'manual_receipts':collected,'courier_receipts':courier,'pending_order_value':sum((o.total for o in orders if o.payment_status in ('pending','cod_pending','failed')),Decimal('0'))}
