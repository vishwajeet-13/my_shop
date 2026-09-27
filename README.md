# My Shop

Voice billing for Frappe. Speak an order, get a draft Sales Invoice.

## Demo

    cd ~/company_projects/sep_bench
    bench start

Open **http://localhost:8013/voice** in Chrome. Log in as `Administrator` / `admin`.

Tap the mic and say:

> "five nut bolt and three wood screw and two claw hammer"

Hinglish works too:

> "paanch nut bolt teen wood screw do dozen washer"

Tap **Create Invoice**. A real draft Sales Invoice appears, editable in Desk,
printable on the shop's own Print Format.

## How it works

    transcript -> parse_transcript()  -> [(qty, phrase), ...]
                -> match_item()       -> fuzzy match against this shop's Item list
                -> create_invoice()   -> draft Sales Invoice

- `my_shop/parser.py` splits speech into quantity and item phrases. Understands
  digits, English number words, and romanised Hindi (ek, do, teen, paanch, das).
  Folds adjacent numbers, so "two dozen" is 24 and "twenty five" is 25.
- `my_shop/api.py` builds the Sales Invoice.
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
an optional Item Group to limit matching to, and the speech language.

## Known limits

- The mic needs a secure context. `localhost` counts, so Chrome on this machine
  works. Opening the page from a phone over a LAN IP will not get mic access;
  put an HTTPS tunnel in front of it for that.
- Voice input is Chrome only. The transcript box is always typeable as a fallback.
