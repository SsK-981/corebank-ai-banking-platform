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
