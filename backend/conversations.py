"""Conversation persistence and security-conscious audit logging."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AuditLog, ChatMessage, Conversation


def get_or_create_conversation(
    db: Session, owner_subject: str, conversation_id: str | None
) -> Conversation:
    if conversation_id:
        conversation = db.scalar(
            select(Conversation).where(Conversation.conversation_id == conversation_id)
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation.owner_subject != owner_subject:
            raise HTTPException(status_code=403, detail="Conversation access denied")
        return conversation
    conversation = Conversation(
        conversation_id=str(uuid4()), owner_subject=owner_subject, status="open"
    )
    db.add(conversation)
    return conversation


def add_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> ChatMessage:
    message = ChatMessage(
        message_id=str(uuid4()),
        conversation_id=conversation_id,
        role=role,
        content=content,
        metadata_json=json.dumps(metadata or {}, default=str),
    )
    db.add(message)
    return message


def add_audit_log(
    db: Session,
    *,
    actor_subject: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
) -> AuditLog:
    audit = AuditLog(
        actor_subject=actor_subject,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details_json=json.dumps(details or {}, default=str),
    )
    db.add(audit)
    return audit
