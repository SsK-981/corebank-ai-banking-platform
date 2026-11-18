CREATE TABLE saved_recipient (
    owner_id BIGINT NOT NULL REFERENCES app_user(id),
    recipient_account_id BIGINT NOT NULL REFERENCES bank_account(account_id),
    PRIMARY KEY (owner_id, recipient_account_id)
);
