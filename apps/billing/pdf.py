"""Downloadable documents from frozen financial snapshots, without remote fetches."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from django.conf import settings
from .presentation import receipt_details


def _document(title, paragraphs, rows):
    font = 'AnnamReceipt'
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font, str(Path(settings.BASE_DIR) / 'resources/fonts/DejaVuSans.ttf')))
    stream = BytesIO()
    style = ParagraphStyle('receipt', fontName=font, fontSize=10, leading=15, wordWrap='CJK')
    def para(value):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)
    story = [para(title), Spacer(1, 12)]
    for value in paragraphs:
        if value:
            story.extend([para(value), Spacer(1, 6)])
    table = Table([[para(a), para(b)] for a,b in rows], colWidths=[350, 145], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),1,colors.grey),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story.append(table)
    SimpleDocTemplate(stream, title=title, author='Annam Foods', leftMargin=40, rightMargin=40).build(story)
    return stream.getvalue()


def invoice_pdf(invoice):
    bill = receipt_details(invoice)
    seller, buyer = invoice.seller, invoice.buyer
    details = [seller.get('name'), seller.get('address'),
               f"{seller.get('state', '')} · State code {seller.get('state_code', '')}",
               f"GSTIN: {seller.get('gstin', '')} · FSSAI: {seller.get('fssai_no', '')}",
               f'Issued: {invoice.issued_at:%d %b %Y}',
               f"Order: {buyer.get('order_no', '')}", buyer.get('name'), buyer.get('phone'),
               buyer.get('business_name'), buyer.get('gstin'), buyer.get('billing_address'),
               ', '.join(bill['address_lines']),
               f"Payment: {bill['payment_label']} · Reference: {invoice.payment_ref}"]
    rows = [('Items / taxes', 'Amount')]
    for line in bill['lines']:
        text = f"{line['description']}\n{line['quantity']} × ₹{line['unit_price']}"
        if line.get('sac'):
            text += f" · SAC / HSN {line['sac']}"
        if bill['tax_registered']:
            text += f"\nTaxable ₹{line['taxable']} · GST {line['tax_rate']}%: ₹{line['tax']}"
        if line['discount_amount']:
            text += f"\nDiscount ₹{line['discount_amount']}"
        rows.append((text, f"₹{line['amount']:.2f}"))
    rows.extend([('Taxable value', f'₹{invoice.taxable:.2f}'), ('CGST', f'₹{invoice.cgst:.2f}'),
                 ('SGST', f'₹{invoice.sgst:.2f}'), ('IGST', f'₹{invoice.igst:.2f}'),
                 ('Round off', f'₹{invoice.round_off:.2f}'), ('Total paid', f'₹{invoice.total:.2f}'),
                 (invoice.amount_words, '')])
    if buyer.get('courier_deferred'):
        rows.append(('Courier charges are payable separately after dispatch.', ''))
    if seller.get('gst_mode') == 'composition':
        rows.append(('Composition taxable person, not eligible to collect tax on supplies.', ''))
    rows.append((seller.get('footer', ''), ''))
    return _document(f'{invoice.get_kind_display()} {invoice.number}', details, rows)


def test_receipt_pdf(order):
    rows = [('Simulated items', 'Amount')]
    rows.extend((f"{line['name']} · {line['quantity']} × ₹{line['unit_price']}", f"₹{line['line_total']}") for line in order.items)
    rows.extend([('Delivery', f'₹{order.delivery_fee}'), ('Simulated total', f'₹{order.total}')])
    return _document('TEST / SIMULATED PAYMENT / NOT AN INVOICE',
                     [order.order_no, order.buyer_name, 'No real money collected. No financial invoice number allocated.'], rows)
