# CoreBank Help routing rules

| Customer intent | Expected behavior |
| --- | --- |
| Send money | Offer the Transfer page. The customer reviews the recipient and amount there. |
| Check a transfer already made | Look up the selected or referenced transaction under the current account, or offer matching transactions. |
| View history, balance, or KYC | Read the requested information under the signed-in account. |
| Download a statement | Point to Download statement CSV. |
| File a dispute or support case | Summarize the issue and ask for confirmation. Show the existing case if the selected transaction already has one. |
| Ask for an update | Use the active case or transaction. If there is no clear subject, ask which one the customer means. |
| Correct an account holder name | Explain how to contact support for an administrator to review the correction. |
| Unfamiliar wording | Allow the optional model to suggest a read intent for balance, history, or KYC. CoreBank validates the intent and writes the reply from its records. Low confidence and unsupported intents get a clarification. |

Treat conversation references such as “this” as dependent on the active case or
transaction. For overlapping words, test both requests side by side. “Send
money” and “they didn’t get the money I sent” must follow different paths.

Evaluate candidate classifiers with synthetic CoreBank examples that cover
natural English, Hinglish, follow-ups, and out-of-scope requests. Include the
existing rules with Ollama as the baseline. Check wrong routes and unintended
actions as well as accuracy and response time.
