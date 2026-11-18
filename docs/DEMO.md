# CoreBank demo walkthrough

Run `docker compose up --build` from the repository and open the
[customer portal](http://localhost:8080) after the seed service completes.
The [demo accounts](../README.md#demo-accounts) use synthetic data.

1. **Overview.** Sign in as Amit to see his account balance, recent activity,
   and the CSV statement download.
2. **Transfer.** Copy Rahul’s account number from his Overview. Sign in as
   Neha and enter the number on **Transfer**. Verify the masked name, save
   the recipient for future transfers, and review and confirm a demo transfer.
3. **Activity.** Find the outgoing transfer using its receipt reference.
   Sign in as Rahul to see the corresponding incoming entry.
4. **Transaction support.** Sign in as Amit. Select **Get help** on his failed
   withdrawal to see the recorded decline and whether the account was debited.
5. **Support cases.** Select **Open a support case**, describe the issue, and
   confirm the summary. Open **My cases** to find the case and view its status.
6. **Staff console.** Open [Bank Operations](http://localhost:8080/admin.html)
   and sign in as the demo administrator to review customer KYC or search for an
   account.
