"""Discussions: section-scoped, moderation, offline draft."""

from helpers import SECTION, auth_header, login


def test_discussion_draft_and_moderation(client):
    learner = login(client, "learner-alpha")
    inst = login(client, "instructor-alpha")
    lh = auth_header(learner["token"])
    thr = client.post(
        "/api/v1/discussions/threads",
        headers=lh,
        json={"section_id": SECTION, "title": "Gate A thread"},
    )
    assert thr.status_code == 200
    tid = thr.json()["thread_id"]
    draft = client.post(
        f"/api/v1/discussions/threads/{tid}/posts",
        headers=lh,
        json={"body": "offline draft", "as_draft": True, "client_mutation_id": "mut_disc_draft1"},
    )
    assert draft.status_code == 200
    assert draft.json()["draft"] is True
    post = client.post(
        f"/api/v1/discussions/threads/{tid}/posts",
        headers=lh,
        json={"body": "published"},
    )
    assert post.status_code == 200
    pid = post.json()["post_id"]
    mod = client.post(
        f"/api/v1/discussions/posts/{pid}/moderate",
        headers=auth_header(inst["token"]),
        json={"note": "ok", "delete": False},
    )
    assert mod.status_code == 200
