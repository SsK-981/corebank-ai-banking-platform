# Fintech AI project state

## Current branch

`feat/customer-workspace` is based on GitHub `main` at `9adb7ec`. The
existing developer checkout was left intact, including its local chatbot outage
changes. The customer portal is the demo entry point at the CoreBank origin.

## Implemented

- Responsive CoreBank workspace with one-click seeded sign-in, overview,
  reviewed internal transfers, receipt references, activity, CSV statements,
  and an embedded support panel.
- The portal keeps the current Basic credential in tab session storage and
  drops it at sign-out. Spring derives the Help identity from its authenticated
  principal and sends it to FastAPI with a separate internal service credential.
  Help is enabled for mapped seeded users in the local demo. The standalone
  Streamlit tool and bank admin portal are still available.
- Documented the no-API-key Docker Compose walkthrough and added a CI step
  for the live, authenticated Help endpoint.

## Verification

- Python suite: 63 passed, one opt-in test skipped. The opt-in test passed
  separately against live seeded CoreBank.
- Java suite: 19 passed using JDK 21 and H2.
- Chrome desktop: demo login, review and send a transfer, receipt in Activity,
  reload, withdrawal, CSV export, ticket, sign-out, and new customer registration.
- Chrome mobile: demo login and Help, with no horizontal overflow at 390px.
- The browser used local Spring Boot/H2 and FastAPI/SQLite processes. The
  Docker Compose/PostgreSQL launch still needs a clean-machine check.

## Pending

After reviewing the branch, publish it to the existing GitHub repository and
verify the Docker Compose quick start. Extending Help to newly registered
customers requires replacing the seeded identity map and provisioning support
records for those identities.

## Manual testing accounts

Use U001 (Rahul), U002 (Amit), and U003 (Neha) as the stable test identities
across portal, integrated Help, and CoreBank-mode Streamlit. The sign-in picker
and docs/MANUAL_TESTING.md describe the fixture. Demo credentials and identities
are fixed, while account numbers are generated per database. An isolated local
manual-testing instance was seeded with a persistent H2 and SQLite database.
Live Chrome checks confirmed all three picker identities in Overview and Help
after signing out and switching. The Python suite and opt-in live test passed.

## Recipient preview

The transfer form looks up a complete recipient number from the signed-in
customer's active source account and displays a masked name. Review repeats
the lookup for the current source and recipient and shows the name with the
amount. Unknown and closed destinations share an unavailable response.
Verified with 20 Java tests and a Chrome walkthrough on a fresh synthetic
database. The persistent localhost instance was restarted with its existing
test accounts and verified to return Neha's masked name without a transfer.

## Local load and failure testing

Tested a separate H2/SQLite instance at the code state of 346fdb2, with
1,003 customer accounts and 110,009 starting transaction rows. Timed 480
mixed API requests (50% history, 25% account lists, 15% recipient previews,
10% transfers). No mixed requests failed. At concurrency 1/10/30, p95 was
116/146/415 ms and throughput was 8.8/76.5/80.7 requests per second. A separate
local-mode Help batch at concurrency 10 returned 30/30 answers with p95 232 ms.
History pagination succeeded through page 401 on an account with 10,100 entries.
The persistent manual-testing instance was excluded from this run.

A 20-request burst against one ₹5,000 source posted 12 transfers of ₹400,
returned six conflicts and two validation rejections, and left ₹200. Receiver
credits summed to ₹4,800. Insufficient funds and same-account transfers were
rejected, and another customer's history returned 403. Replaying an identical
₹75 transfer posted twice with two references. A successful customer transfer
response included the recipient balance and email. Prioritize a minimal transfer
receipt and durable idempotency, then profile the authentication and request path
on the production-like PostgreSQL setup. The local test used no external model
and did not establish production capacity. No application code changed.

## Retry-safe transfers

Customer transfers now acquire source and recipient PostgreSQL row locks in
account-ID order. An optional `Idempotency-Key` binds the authenticated customer
to the source, recipient, and amount. When supplied, CoreBank records the
posted receipt or insufficient-funds decline in the same transaction as its
balance changes or failed attempt. Requests without a key remain supported.
Customer receipts now return only the masked recipient name in `toAccount`.

The portal retains one unconfirmed request per customer in tab session
storage. **Retry transfer** uses the same key and payload after a timeout or
reload, then refreshes account balances after receiving a receipt.

Verified the Java suite on H2 and PostgreSQL 17.11 (23 passing on each).
Twenty distinct ₹400 requests against ₹5,000 posted 12 transfers, declined
eight for insufficient funds, and left ₹200. Twenty requests with the same
key posted one debit and credit, returned one receipt, and left ₹4,600.
A rejected instruction stayed rejected after a top-up. A Chrome test dropped
a successful PostgreSQL-backed response and recovered the original receipt
after reloading, with one ₹400 movement. This run verified correctness rather
than repeating the large-data throughput benchmark. The ongoing manual H2
instance was migrated in place using its existing fixture data.
