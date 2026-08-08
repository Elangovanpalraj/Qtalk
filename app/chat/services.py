# app/chat/services.py
from app.chat.models import Message, Poll, PollOption, PollVote

def forward_message_logic(db, message_id, target_group_id, sender_id):
    original_msg = db.query(Message).filter(Message.id == message_id).first()
    if not original_msg: return None
    new_message = Message(
        sender_id=sender_id, group_id=target_group_id,
        content=original_msg.content, msg_type=original_msg.msg_type,
        is_forwarded=True
    )
    db.add(new_message)
    db.commit()
    return new_message

# (Poll logic-um inga add pannunga)
