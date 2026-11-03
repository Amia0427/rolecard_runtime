from __future__ import annotations

from pathlib import Path

from astrbot_plugin_rolecard_runtime.state_store import StateStore


def test_state_store_isolates_members_and_nsfw_scope(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "runtime.sqlite3")
    initial = {
        "relation_stage": "初识",
        "trust": 0,
        "dependency": 0,
        "feminine_acceptance": 10,
        "lust": None,
        "active_event": None,
        "event_step": 0,
        "completed_events": [],
        "flags": {},
    }
    session = "group:GroupMessage:42"
    member_a = store.state(session, "a", "card", initial)
    member_a["trust"] = 10
    store.save_state(session, "a", "card", member_a)
    member_b = store.state(session, "b", "card", initial)
    member_b["trust"] = 3
    store.save_state(session, "b", "card", member_b)
    store.set_nsfw("private:FriendMessage:a", "a", True)

    assert store.state(session, "a", "card", initial)["trust"] == 10
    assert store.state(session, "b", "card", initial)["trust"] == 3
    assert store.nsfw_enabled("private:FriendMessage:a", "a")
    assert not store.nsfw_enabled(session, "a")
    assert len(store.state_rows(session, "a", "card")) == 1
    store.reset_state(session, "a", "card")
    assert store.state(session, "a", "card", initial)["trust"] == 0
    store.close()


def test_unbinding_keeps_member_state_and_other_session_bindings(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "runtime.sqlite3")
    session = "bot:FriendMessage:123"
    other_session = "bot:FriendMessage:456"
    store.bind(session, "card")
    store.bind(other_session, "card")
    store.save_state(session, "123", "card", {"trust": 42})
    store.set_nsfw(session, "123", True)

    store.bind(session, None)

    assert store.binding(session) is None
    assert store.binding(other_session) == "card"
    assert store.state_rows(session)[0]["state"]["trust"] == 42
    assert store.nsfw_enabled(session, "123")
    assert store.has_binding("card")
    store.bind(other_session, None)
    assert not store.has_binding("card")
    store.close()
