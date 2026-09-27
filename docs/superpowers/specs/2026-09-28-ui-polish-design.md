# UI polish: /voice and /invoice

## Goal

Refine the existing warm "paper receipt" look of both portal pages. Visual only:
no change to API calls, page controllers, or invoice data.

## Structure

- `my_shop/public/css/shop.css`: shared tokens (colour, type, radius, shadow),
  light + dark palettes, and components used by both pages (sheet, buttons,
  receipt grid, total, stamp, logo mark).
- Each page loads it via `{% block style %}` plus Google Fonts (Fraunces for
  headings, JetBrains Mono for numbers). Page-specific rules stay inline.
- All classes are `ms-` prefixed. Frappe's Bootstrap defines `.btn`, `.card`,
  `.row` and `.mark`, which currently break button padding, row alignment and
  the PAID stamp width.

## /voice

- Header with logo mark, shop name, tagline.
- Mic button: SVG icon; idle, listening (expanding rings), unsupported, error states.
- Example phrases as chips that fill the transcript box.
- Bill editor and billed result styled as a receipt; panel eases in.
- Billed state shows a "BILLED" stamp and the invoice number.

## /invoice

- Receipt with serrated bottom edge, cleaner meta block, item names that wrap
  under a mobile-friendly grid, natural-width rotated PAID stamp.
- Print: white background, no shadow, no action bar, no colour fills.

## Cross-cutting

- Dark mode via `prefers-color-scheme` (warm charcoal, cream ink, same rust).
- Works at 360px wide; visible focus rings; `prefers-reduced-motion` disables animation.

## Verification

Playwright screenshots before/after at desktop, mobile, dark, and print; run a
full order (preview → add missing item → create → invoice page) with no new JS errors.
