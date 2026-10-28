import csv
from datetime import datetime, time, timedelta
from django import forms
from django.http import HttpResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from .access import owner_required
from apps.orders.reports import report_data,daily_sales
from apps.orders.models import Order
from apps.orders.services import OrderError
from apps.orders.courier import record_dispatch,confirm_courier_payment,release_courier_drafts


class ReportForm(forms.Form):
    start=forms.DateTimeField(input_formats=['%Y-%m-%dT%H:%M','%Y-%m-%dT%H:%M:%S'],widget=forms.DateTimeInput(attrs={'type':'datetime-local','class':'o-input'},format='%Y-%m-%dT%H:%M'))
    end=forms.DateTimeField(input_formats=['%Y-%m-%dT%H:%M','%Y-%m-%dT%H:%M:%S'],widget=forms.DateTimeInput(attrs={'type':'datetime-local','class':'o-input'},format='%Y-%m-%dT%H:%M'))
    meal=forms.ChoiceField(required=False,choices=[('','All food categories'),('breakfast','Breakfast'),('lunch','Lunch'),('dinner','Dinner'),('snacks','Snacks')],widget=forms.Select(attrs={'class':'o-input'}))
    product=forms.CharField(required=False,max_length=120,label='Product name or ID',widget=forms.TextInput(attrs={'class':'o-input'}))
    delivery_date=forms.DateField(required=False,label='Delivery date (optional)',widget=forms.DateInput(attrs={'type':'date','class':'o-input'}))
    include_cancelled=forms.BooleanField(required=False,label='Include cancelled orders')

    def clean(self):
        d=super().clean()
        if d.get('start') and d.get('end') and d['end']<=d['start']:
            raise forms.ValidationError('End must be after start. The end time is excluded from the range.')
        return d


@owner_required
@never_cache
def reports(request):
    now=timezone.localtime();start=now.replace(hour=0,minute=0,second=0,microsecond=0)
    params=request.GET if request.GET else {'start':start.strftime('%Y-%m-%dT%H:%M'),'end':(now+timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M')}
    form=ReportForm(params);data=None
    if form.is_valid():
        data=report_data(**form.cleaned_data)
        if request.GET.get('export')=='csv':
            response=HttpResponse(content_type='text/csv; charset=utf-8');response['Content-Disposition']='attachment; filename="annam-order-report.csv"';response.write('\ufeff')
            writer=csv.writer(response);writer.writerow(['Start (India time, inclusive)',form.cleaned_data['start'].isoformat(),'End (exclusive)',form.cleaned_data['end'].isoformat()]);writer.writerow(['Food category','Product ID','Product','Catalog category','Quantity','Items amount (INR)','Order count'])
            for row in data['rows']:
                # Avoid executable spreadsheet formulas in user-authored product names.
                safe=lambda s: "'"+str(s) if str(s).startswith(('=','+','-','@','\t','\r')) else str(s)
                writer.writerow([safe(row[k]) for k in ['meal','product_id','product','catalog_category','quantity','amount','orders']])
            return response
    return render(request,'owner/reports.html',{'form':form,'report':data,'sales':daily_sales()})


@owner_required
@require_POST
def courier_action(request,pk):
    order=get_object_or_404(Order,pk=pk)
    try:
        action=request.POST.get('action')
        if action=='dispatch':
            record_dispatch(order,amount=request.POST.get('amount'),courier_name=request.POST.get('courier_name',''),tracking_number=request.POST.get('tracking_number',''),actor=f'owner:{request.user.username}')
        elif action=='paid' and request.POST.get('confirmed')=='yes':
            confirm_courier_payment(order,reference=request.POST.get('reference',''),actor=f'owner:{request.user.username}')
        else:raise OrderError('Confirm the action before continuing.')
        messages.success(request,'Courier record updated. WhatsApp drafts are held while notifications are offline.')
    except (OrderError,ValueError) as exc:messages.error(request,str(exc))
    return redirect('owner:order',pk=order.pk)


@owner_required
@require_POST
def release_notices(request):
    try:
        if request.POST.get('confirmed')!='yes':raise OrderError('Confirm that WhatsApp is connected before releasing queued drafts.')
        count=release_courier_drafts(request.tenant);messages.success(request,f'{count} courier messages released to the normal message queue.')
    except OrderError as exc:messages.error(request,str(exc))
    return redirect('owner:checkout_settings')
