# My Shop

Voice billing for Frappe. Speak an order, get a Sales Invoice, track udhaar.

## Demo

    cd ~/company_projects/sep_bench
    bench start

Open **http://localhost:8013/voice** in Chrome. Log in as `Administrator` / `admin`.

Tap the mic and say:

> "five nut bolt and three wood screw and two claw hammer"

Hinglish works too:

> "paanch nut bolt teen wood screw do dozen washer"

Tap **Create Invoice** to review the bill, pick the customer and how they pay,
then **Create Invoice** again. The Sales Invoice is submitted and, for Cash or
UPI, paid in the same step.

## Features

- **Payment mode per bill**: Cash, UPI, or Udhaar (credit). Udhaar needs a
  named customer and leaves the invoice outstanding.
- **Customer picker**: search by name or phone, or add one on the spot with a
  mobile number. Shows what the customer already owes.
- **Discount**: a flat rupee discount on the bill.
- **GST / tax**: set a Sales Taxes and Charges Template in Shop Voice Settings
  and every voice bill gets it.
- **UPI QR**: set your UPI ID in Shop Voice Settings. Picking UPI shows a
  scan-to-pay QR for the exact amount; unpaid bills show one on the invoice page.
- **WhatsApp**: share the bill as a text message, with a UPI pay link when
  something is pending.
- **Khata** (`/khata`): today's sales and cash / UPI collected, everyone who
  owes money with how long it has been pending, a one-tap WhatsApp reminder,
  and **Received** to record a payment (settles the oldest bills first).

## How it works

    transcript -> parse_transcript()  -> [(qty, phrase), ...]
                -> match_item()       -> fuzzy match against this shop's Item list
                -> create_invoice()   -> submitted Sales Invoice (+ payment)

- `my_shop/parser.py` splits speech into quantity and item phrases. Understands
  digits, English number words, and romanised Hindi (ek, do, teen, paanch, das).
  Folds adjacent numbers, so "two dozen" is 24 and "twenty five" is 25.
- `my_shop/api.py` builds the Sales Invoice.
- `my_shop/khata.py` customers, dues, payments received, today's summary.
- `my_shop/payments.py` payment entries, UPI links and QR, WhatsApp links.
- `my_shop/www/voice.html` is the mic page. It uses the browser Web Speech API,
  so there is no speech server and no API key.

Wrong matches are fixed by editing the invoice. That is deliberate: the editable
grid is the error handling, so v1 needs no disambiguation UI.

## Setup on a fresh site

    bench --site localhost install-app my_shop
    bench --site localhost execute my_shop.demo.seed

`demo.seed` creates the company, chart of accounts, price lists, a walk-in
customer, ten hardware items with prices, and fills in Shop Voice Settings.

## Settings

**Shop Voice Settings** (single doctype): shop name, company, default customer,
an optional Item Group to limit matching to, the speech language, your UPI ID,
and an optional sales tax template.

## Tests

    bench --site localhost set-config allow_tests true
    bench --site localhost run-tests --app my_shop

## Known limits

- The mic needs a secure context. `localhost` counts, so Chrome on this machine
  works. Opening the page from a phone over a LAN IP will not get mic access;
  put an HTTPS tunnel in front of it for that.
- Voice input is Chrome only. The transcript box is always typeable as a fallback.
