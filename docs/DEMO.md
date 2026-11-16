# 90-second demo

Run `docker compose up --build` from the repository and open
[CoreBank](http://localhost:8080) after the seed service completes.

1. **Overview.** Select **Try demo account** to sign in as Amit. Show the active account
   and balance.
2. **Transfer.** Use Rahul’s account number from `docker compose logs corebank-seed`.
   Make a small demo transfer and note the reference in the confirmation.
3. **Activity.** Find the new transfer and the seeded failed withdrawal. Download a
   CSV statement if needed.
4. **Help.** In Activity, select **Get help** on Amit’s failed withdrawal. Ask “Why
   did that one fail?” The assistant uses the selected record to explain the decline.
5. **Escalation.** Select **Open a support case**, describe the issue, and confirm the summary. Show the case ID. Use
   **My cases** to find the same case and its status. The standalone
   [operations dashboard](http://localhost:8501) can inspect tickets.

## Suggested interview questions

- How does the support service get the customer identity?
- Which service owns the balance and transaction status?
- What does the customer see if the support service is unavailable?
- How do transactional transfers and optimistic locking protect balances?
