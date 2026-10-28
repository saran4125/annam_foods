from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404,redirect,render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods,require_POST
from .views import guest_order
from .models import CourierPayment
from apps.orders.models import CourierCharge
from . import courier
from .provider import PaymentError


def guest_payment(request,reference):
    order=guest_order(request,reference)
    return get_object_or_404(CourierPayment.objects.select_related('charge__order','connection'),charge__order=order,provider_order_id=request.POST.get('razorpay_order_id') or request.GET.get('provider_order',''))


@never_cache
@require_POST
def begin(request,reference):
    order=guest_order(request,reference)
    try:
        intent=courier.start(get_object_or_404(CourierCharge.objects,order=order))
    except (PaymentError,RuntimeError) as exc:
        messages.error(request,str(exc) if isinstance(exc,PaymentError) else 'Payment credentials are unavailable.')
        return redirect('storefront:checkout_complete',reference=reference)
    return redirect(f'{request.path}view/?provider_order={intent.provider_order_id}')


@never_cache
@require_http_methods(['GET'])
def payment(request,reference):
    intent=guest_payment(request,reference)
    if intent.state!='ready':return redirect('storefront:checkout_complete',reference=reference)
    options={'key':intent.key_id,'order_id':intent.provider_order_id,'amount':intent.amount,'currency':intent.currency,
        'name':request.tenant.config.brand_name or request.tenant.name,'description':'Courier charge for '+intent.charge.order.order_no}
    return render(request,'payments/courier_payment.html',{'intent':intent,'reference':reference,'options':options})


@never_cache
@require_POST
def verify(request,reference):
    intent=guest_payment(request,reference)
    try:courier.verify(intent,request.POST.get('razorpay_order_id',''),request.POST.get('razorpay_payment_id',''),request.POST.get('razorpay_signature',''))
    except (PaymentError,RuntimeError) as exc:return JsonResponse({'error':str(exc) if isinstance(exc,PaymentError) else 'Payment credentials are unavailable.'},status=400)
    intent.refresh_from_db();return JsonResponse({'paid':intent.state=='captured','test':intent.mode=='test','status':intent.state})


@never_cache
@require_http_methods(['GET','POST'])
def status(request,reference):
    intent=guest_payment(request,reference)
    if request.method=='POST':
        try:courier.reconcile(intent)
        except (PaymentError,RuntimeError):return JsonResponse({'error':'Courier payment verification is pending.'},status=503)
    intent.refresh_from_db();return JsonResponse({'paid':intent.state=='captured','test':intent.mode=='test','status':intent.state})
