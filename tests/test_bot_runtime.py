import asyncio

from bale_inviter.adapters.bale import BotInboundMessage
from bale_inviter.adapters.fake import FakeBaleAdapter
from bale_inviter.database.models import Contact
from bale_inviter.domain.enums import BaleAccountStatus, DirectInviteStatus
from bale_inviter.services.bot_runtime import BotRuntime


def test_start_sends_invite_text_and_auto_invites(session, settings) -> None:
    adapter = FakeBaleAdapter(
        inbound=[
            BotInboundMessage(
                update_id=1,
                user_id="909",
                chat_id="909",
                chat_type="private",
                text="/start",
                is_start=True,
            )
        ]
    )
    runtime = BotRuntime(session, adapter, settings)
    handled = asyncio.run(runtime.process_inbound())
    assert handled == 1
    assert adapter.send_text_calls
    assert adapter.direct_invite_calls
    assert adapter.direct_invite_calls[0][2] == "909"


def test_shared_contact_matches_and_invites(session, settings) -> None:
    contact = Contact(
        name="Colleague",
        phone="09125550000",
        normalized_phone="+989125550000",
        is_valid=True,
        import_fingerprint="fp-runtime-1",
    )
    session.add(contact)
    session.flush()
    adapter = FakeBaleAdapter(
        inbound=[
            BotInboundMessage(
                update_id=2,
                user_id="808",
                chat_id="808",
                chat_type="private",
                phone="+989125550000",
            )
        ]
    )
    runtime = BotRuntime(session, adapter, settings)
    asyncio.run(runtime.process_inbound())
    session.refresh(contact)
    assert contact.bale_user_id == "808"
    assert contact.bale_account_status is BaleAccountStatus.HAS_ACCOUNT
    assert contact.direct_invite_status is DirectInviteStatus.SUCCESS


def test_group_message_does_not_send_dm(session, settings) -> None:
    adapter = FakeBaleAdapter(
        inbound=[
            BotInboundMessage(
                update_id=3,
                user_id="1",
                chat_id="-1009",
                chat_type="supergroup",
                chat_title="Team",
                text="hello",
            )
        ]
    )
    runtime = BotRuntime(session, adapter, settings)
    asyncio.run(runtime.process_inbound())
    assert adapter.send_text_calls == []
    assert adapter.direct_invite_calls == []
