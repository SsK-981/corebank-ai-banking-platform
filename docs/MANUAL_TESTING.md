# Manual testing accounts

Start the local demo with `docker compose up --build` and let `corebank-seed`
finish. Open [the customer portal](http://localhost:8080), select a customer,
and click **Try demo account**. Sign out before switching. The default local
password for all four test logins is `password123`.

| Test identity | Sign-in email | Fresh CoreBank seed | Use it for |
| --- | --- | --- | --- |
| Rahul Sharma (U001) | `rahul@example.com` | Verified, ₹15,750 | Receive a transfer and check the incoming entry |
| Amit Verma (U002) | `amit@example.com` | Pending, ₹24,550 | Review a failed withdrawal, ask Help about KYC, and create a ticket |
| Neha Patil (U003) | `neha@example.com` | Verified, ₹38,500 | Send a transfer and check the balance and receipt |
| Demo Administrator | `demo.admin@corebank.local` | Staff access | Set a customer's KYC and verify it in Help |

Use [Staff access](http://localhost:8080/admin.html) for the admin login. In
standalone Streamlit with the Compose configuration, select the same U001,
U002, or U003 identity. Each ID resolves to the same CoreBank customer.

## First manual pass

1. As Rahul, copy the account number from Overview. Sign out.
2. As Neha, enter that number and confirm that **Recipient: Rahul S•••**
   appears. Choose **Review transfer**, confirm the name and amount, then send
   ₹500. Check the outgoing entry in Activity.
3. Sign in as Rahul and check that ₹500 appears as an incoming transfer.
4. As Amit, ask Help “What is my KYC status?” and confirm it says pending
   on a fresh database. In Activity, choose **Get help** on the failed withdrawal,
   ask why it failed, then open and confirm a support case. Use **My cases** to
   check the same case later.

Names, sign-ins, and customer IDs are fixed across fresh seeds. Account
numbers and transaction references are generated for each database. Use the
number shown in Overview for transfers. Balances and history change as you
test. `docker compose down` preserves the Compose database volumes and test
history.
