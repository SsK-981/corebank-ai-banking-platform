# 90-second demo

Run `docker compose up --build` from the repository and open
[CoreBank](http://localhost:8080) after the seed service completes.

1. **Overview.** Select **Try demo account** to sign in as Amit. Show the active account
   and balance.
2. **Transfer.** Use Rahul’s account number from `docker compose logs corebank-seed`.
   Make a small demo transfer and note the reference in the confirmation.
3. **Activity.** Find the new transfer and the seeded failed withdrawal. Download a
   CSV statement if needed.
4. **Help.** Ask “Show my transactions” or “What is my KYC status?” from the same
   portal. Expand agent activity to see the tool used.
5. **Escalation.** Ask “Open a support ticket for my failed withdrawal.” Show the ticket
   ID. The standalone [operations dashboard](http://localhost:8501) can inspect tickets.

## Suggested interview questions

- How does the support service get the customer identity?
- Which service owns the balance and transaction status?
- What does the customer see if the support service is unavailable?
- How do transactional transfers and optimistic locking protect balances?
