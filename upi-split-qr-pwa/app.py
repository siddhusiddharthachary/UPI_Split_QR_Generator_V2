#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
import os
import base64
import html
import re
import time
import json
import qrcode

HOST = '0.0.0.0'
PORT = int(os.environ.get('PORT', '8080'))
MAX_CHUNK = Decimal('1999.00')
UPI_RE = re.compile(r'^[A-Za-z0-9._-]{2,256}@[A-Za-z0-9.-]{2,64}$')


def split_amount(total: Decimal):
    total = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    parts = []
    remaining = total
    while remaining > MAX_CHUNK:
        parts.append(MAX_CHUNK)
        remaining -= MAX_CHUNK
    if remaining > 0:
        parts.append(remaining)
    return parts


def build_upi_uri(upi_id: str, amount: Decimal, idx: int):
    # pn is required in standard merchant dynamic QR. We derive a display label
    # from the UPI ID because the requested UI only asks for UPI ID + amount.
    payee_label = upi_id.split('@', 1)[0].replace('.', ' ').replace('_', ' ').strip() or 'UPI Payee'
    ref = f"SPLIT{int(time.time())}{idx:02d}"
    params = {
        'pa': upi_id,
        'pn': payee_label[:40],
        'tr': ref,
        'tn': f'Split payment {idx}',
        'am': f'{amount:.2f}',
        'cu': 'INR',
    }
    return 'upi://pay?' + urlencode(params)


def make_icon(size: int):
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (size, size), 'white')
    d = ImageDraw.Draw(img)
    pad = size // 8
    d.rounded_rectangle((pad, pad, size-pad, size-pad), radius=size//10, fill='#111827')
    # Simple QR-like mark, intentionally not a scannable payment QR.
    unit = size // 12
    for x, y in [(3,3),(7,3),(3,7)]:
        x0,y0=x*unit,y*unit
        d.rectangle((x0,y0,x0+2*unit,y0+2*unit), outline='white', width=max(2,unit//3))
    out=BytesIO(); img.save(out, format='PNG'); return out.getvalue()


def qr_data_uri(text: str):
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    out = BytesIO()
    img.save(out, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode('ascii')


def page(body: str, error: str = ''):
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ''
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UPI Split QR Generator</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#111827">
<link rel="apple-touch-icon" href="/icon-192.png">
<style>
:root {{ font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; color: #171717; background: #f5f7fb; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 32px 16px; }}
.container {{ max-width: 980px; margin: 0 auto; }}
.hero {{ margin-bottom: 20px; }}
h1 {{ margin: 0 0 8px; font-size: clamp(28px, 4vw, 44px); }}
.sub {{ color: #5d6470; line-height: 1.55; }}
.card {{ background: white; border: 1px solid #e4e7ec; border-radius: 18px; padding: 22px; box-shadow: 0 8px 30px rgba(0,0,0,.05); }}
form {{ display: grid; grid-template-columns: 1fr 220px auto; gap: 12px; align-items: end; }}
label {{ font-size: 13px; font-weight: 700; display: block; margin-bottom: 7px; }}
input {{ width: 100%; height: 46px; border: 1px solid #cfd4dc; border-radius: 10px; padding: 0 12px; font-size: 16px; }}
button {{ height: 46px; border: 0; border-radius: 10px; padding: 0 18px; font-size: 15px; font-weight: 800; background: #111827; color: white; cursor: pointer; }}
.note {{ margin-top: 12px; font-size: 13px; color: #68707d; }}
.error {{ margin-bottom: 14px; padding: 12px 14px; border-radius: 10px; background: #fff1f1; color: #9b1c1c; border: 1px solid #ffd0d0; }}
.results {{ margin-top: 22px; }}
.summary {{ margin-bottom: 14px; font-weight: 700; }}
.qrgrid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(250px,1fr)); gap: 16px; }}
.qrcard {{ background: white; border: 1px solid #e4e7ec; border-radius: 16px; padding: 18px; text-align: center; }}
.qrcard img {{ width: 220px; max-width: 100%; image-rendering: crisp-edges; }}
.amount {{ font-size: 28px; font-weight: 900; margin: 10px 0 4px; }}
.receiver {{ color: #68707d; word-break: break-all; font-size: 13px; }}
.paylink {{ display: inline-block; margin-top: 12px; padding: 10px 14px; border-radius: 10px; background: #eef2ff; color: #27346a; font-weight: 800; text-decoration: none; }}
.disclaimer {{ margin-top: 18px; padding: 14px; background: #fffbeb; border: 1px solid #f7e5a3; border-radius: 12px; color: #67591a; font-size: 13px; line-height: 1.5; }}
@media (max-width: 760px) {{ form {{ grid-template-columns: 1fr; }} button {{ width: 100%; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="hero">
    <h1>UPI Split QR Generator</h1>
    <div class="sub">Enter a receiver UPI ID and total amount. Payments above ₹1,999 are automatically split into multiple QR codes.</div>
  </div>
  {error_html}
  <div class="card">
    <form method="post" action="/generate">
      <div>
        <label for="upi">Receiver UPI ID</label>
        <input id="upi" name="upi" placeholder="example@upi" required autocomplete="off">
      </div>
      <div>
        <label for="amount">Total amount (₹)</label>
        <input id="amount" name="amount" type="number" min="0.01" step="0.01" placeholder="5997" required>
      </div>
      <button type="submit">Generate QRs</button>
    </form>
    <div class="note">For interoperable PhonePe / Google Pay / Paytm scanning, use a valid UPI ID (VPA). A raw bank-account number alone cannot be used as the payee address in a standard UPI payment QR.</div>
  </div>
  {body}
</div>
<script>
if ('serviceWorker' in navigator) {{
  window.addEventListener('load', () => navigator.serviceWorker.register('/service-worker.js'));
}}
</script>
</body>
</html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            self._send(page(''))
        elif path == '/manifest.json':
            self._send_bytes(json.dumps({
                'name': 'UPI Split QR Generator',
                'short_name': 'UPI Split QR',
                'start_url': '/',
                'display': 'standalone',
                'background_color': '#f5f7fb',
                'theme_color': '#111827',
                'icons': [
                    {'src': '/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
                    {'src': '/icon-512.png', 'sizes': '512x512', 'type': 'image/png'}
                ]
            }), content_type='application/manifest+json')
        elif path == '/service-worker.js':
            js = """const CACHE='upi-split-v1';
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(['/']))));
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{if(e.request.method==='GET')e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));});
"""
            self._send_bytes(js, content_type='application/javascript; charset=utf-8')
        elif path in ('/icon-192.png', '/icon-512.png'):
            size = 192 if '192' in path else 512
            self._send_bytes(make_icon(size), content_type='image/png')
        else:
            self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != '/generate':
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length).decode('utf-8', errors='replace')
        form = parse_qs(raw)
        upi = form.get('upi', [''])[0].strip()
        amount_raw = form.get('amount', [''])[0].strip()

        if not UPI_RE.match(upi):
            self._send(page('', 'Please enter a valid UPI ID, for example name@bank.'))
            return
        try:
            total = Decimal(amount_raw)
            if total <= 0:
                raise InvalidOperation
            total = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            self._send(page('', 'Please enter a valid payment amount greater than ₹0.'))
            return

        parts = split_amount(total)
        cards = []
        for i, part in enumerate(parts, start=1):
            uri = build_upi_uri(upi, part, i)
            qr = qr_data_uri(uri)
            cards.append(f'''<div class="qrcard">
              <img src="{qr}" alt="QR for payment {i}">
              <div class="amount">₹{part:.2f}</div>
              <div class="receiver">{html.escape(upi)}</div>
              <a class="paylink" href="{html.escape(uri, quote=True)}">Open in UPI app</a>
            </div>''')

        body = f'''<div class="results">
          <div class="summary">₹{total:.2f} → {len(parts)} QR code{'s' if len(parts) != 1 else ''}</div>
          <div class="qrgrid">{''.join(cards)}</div>
          <div class="disclaimer">The QR opens a UPI payment request with the receiver and amount prefilled. The payer still reviews and authorizes the transaction inside their UPI app using their normal UPI PIN. The app does not collect or store the payer's PIN.</div>
        </div>'''
        self._send(page(body))

    def _send(self, content):
        self._send_bytes(content, content_type='text/html; charset=utf-8')

    def _send_bytes(self, content, content_type='text/plain; charset=utf-8'):
        data = content.encode('utf-8') if isinstance(content, str) else content
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print('[server]', fmt % args)


if __name__ == '__main__':
    print(f'UPI Split QR app running at http://{HOST}:{PORT}')
    print('Press Ctrl+C to stop.')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
