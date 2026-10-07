# V79 WiPay Sandbox Runbook

This runbook activates WiPay **sandbox only** for V79 Hub, V79 Academy and V79 Tiquet.

## Safety rules

- Keep `WIPAY_ENV=sandbox` until WiPay supplies the approved Saint Lucia production account number, API key, endpoint, country code and currency.
- Sandbox payments are recorded as test orders only. They must never extend Hub subscriptions, unlock Academy paid courses or post Tiquet/FFPRO revenue.
- Do not reuse launch secrets or the general platform secret for the dedicated Academy/Tiquet billing service keys.
- Keep all secrets in server `.env` files. Never commit them.

## 1. Generate three independent secrets

Run on the server:

```bash
openssl rand -hex 32   # V79_BILLING_STATE_SECRET
openssl rand -hex 32   # V79_ACADEMY_BILLING_SECRET
openssl rand -hex 32   # V79_TIQUET_BILLING_SECRET
```

Copy each value to the matching applications as described below.

## 2. Hub configuration

In the Hub production `.env`:

```dotenv
ACADEMY_PUBLIC_URL=https://v79academy.v79sl.com

WIPAY_ENABLED=1
WIPAY_ENV=sandbox
WIPAY_SANDBOX_DOC_DEFAULTS=1
WIPAY_FEE_STRUCTURE=merchant_absorb
WIPAY_RESPONSE_URL=https://hub.v79sl.com/api/billing/wipay/return

V79_BILLING_STATE_SECRET=<first-generated-secret>
V79_ACADEMY_BILLING_SECRET=<second-generated-secret>
V79_TIQUET_BILLING_SECRET=<third-generated-secret>
```

For sandbox, the provider module uses WiPay's published test account `1234567890`, API key `123`, TT endpoint and TTD unless explicit sandbox values are supplied.

## 3. Academy configuration

In the Academy production `.env`:

```dotenv
V79_HUB_BILLING_URL=http://v79-hub:3040
V79_ACADEMY_BILLING_SECRET=<same-second-generated-secret>
V79_ACADEMY_BILLING_CURRENCY=XCD
```

The Hub will report WiPay sandbox capability separately from the Academy source currency. Sandbox testing may therefore run through WiPay's test currency, but no sandbox payment can unlock a course.

## 4. Tiquet configuration

In the Tiquet production `.env`:

```dotenv
V79_HUB_BILLING_URL=http://v79-hub:3040
V79_TIQUET_BILLING_SECRET=<same-third-generated-secret>
```

Tiquet sends each invoice's configured business currency to Hub. Live checkout will be hidden if the merchant currency does not match.

## 5. Deployment order

Deploy/recreate in this order so connected apps never point at an older Hub contract:

1. V79 Hub
2. V79 Academy
3. V79 Tiquet

Confirm all three share `proxy_network` and can resolve `v79-hub:3040`.

## 6. Hub sandbox smoke test

Sign into Hub with a user who has billing permission and open **Plans & Billing**.

Expected:
- WiPay shows **sandbox**.
- A **Open WiPay test checkout** button appears even if the Hub plan is still Beta/custom.
- The checkout amount is a fixed **10.00 TTD** when the documented sandbox defaults are used.
- After an approved sandbox card, Hub shows payment verified with a sandbox/test message.
- The Hub renewal date and entitlements do not change.

WiPay currently documents these sandbox cards:
- Approved Mastercard: `5111111111111111`
- Declined Mastercard: `5111111111113333`
- Approved Visa: `4111111111111111`
- Declined Visa: `4111111111113333`

Any expiry date and any 3-digit CVV may be used in WiPay sandbox according to their current developer documentation.

## 7. Academy smoke test

Open a premium one-time course while signed in as a learner.

Expected:
- The paywall reports WiPay sandbox is active.
- Checkout can be opened when Hub reports billing ready.
- A successful sandbox transaction is verified but returns `SANDBOX_PAYMENT_VERIFIED`.
- The course remains locked because sandbox transactions never create live ownership.

## 8. Tiquet smoke test

Use a V79 Digital client portal link.

Expected:
- Deposit payment is unavailable until the quote is approved.
- Final payment is unavailable until the job is invoiced/completed.
- WiPay sandbox is visibly labelled.
- A successful sandbox transaction is verified but is not inserted into the real Tiquet cash ledger and is not sent to FFPRO.

Other SMB tenant workspaces must not be able to create WiPay invoice orders through the V79 Digital merchant account.

## 9. Live cutover gate

Do not switch to `WIPAY_ENV=live` until WiPay provides and confirms all of the following for the approved Saint Lucia merchant:

- live account number
- live API key
- production payment-request endpoint
- accepted country code
- accepted settlement/transaction currency
- confirmation that Hub/Aggregated Academy prices can be charged in XCD (Hub self-service remains disabled if the live merchant currency is not XCD)
- fee structure expectations
- callback/verification requirements
- whether recurring/tokenized billing is supported for Academy/Hub subscriptions
- whether marketplace/sub-merchant settlement is supported before enabling Tiquet payments for customer SMB tenants

Before switching environments, let any in-flight sandbox checkout finish or expire so a callback is never verified against the wrong environment key. When the live values are known, replace the sandbox configuration and perform a low-value live transaction before enabling customer-facing payment buttons broadly.
