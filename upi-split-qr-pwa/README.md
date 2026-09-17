# UPI Split QR Generator - PWA

Installable Progressive Web App that splits a total into payment chunks of at most INR 1,999 and generates a UPI payment QR for each chunk.

## Run locally / Codespaces

```bash
pip install -r requirements.txt
python app.py
```

Open port 8080. For PWA installation in production, deploy over HTTPS. The browser can then offer Install App / Add to Home Screen.

## Important

Use a valid UPI ID (VPA). The payer must verify the receiver and amount and authorize payment in their UPI app. This project does not collect UPI PINs.
