"""Groups + auth isolation."""

from helpers import SECTION, auth_header, login, user_id


def test_group_shared_submission_isolation(client):
    inst = login(client, "instructor-alpha")
    a = login(client, "learner-alpha")
    b = login(client, "learner-beta")
    g1 = client.post(
        "/api/v1/groups",
        headers=auth_header(inst["token"]),
        json={
            "section_id": SECTION,
            "name": "Group 1",
            "member_ids": [user_id(a)],
        },
    )
    assert g1.status_code == 200
    g2 = client.post(
        "/api/v1/groups",
        headers=auth_header(inst["token"]),
        json={
            "section_id": SECTION,
            "name": "Group 2",
            "member_ids": [user_id(b)],
        },
    )
    assert g2.status_code == 200
    gid1, gid2 = g1.json()["group_id"], g2.json()["group_id"]
    sub = client.post(
        f"/api/v1/groups/{gid1}/submissions",
        headers=auth_header(a["token"]),
        json={
            "activity_id": "act1",
            "activity_type": "assignment",
            "payload": {"text": "shared"},
            "contributions": [{"user_id": user_id(a), "pct": 100}],
        },
    )
    assert sub.status_code == 200
    # Peer in other group cannot list
    denied = client.get(
        f"/api/v1/groups/{gid1}/submissions",
        headers=auth_header(b["token"]),
    )
    assert denied.status_code == 403
    ok = client.get(
        f"/api/v1/groups/{gid1}/submissions",
        headers=auth_header(a["token"]),
    )
    assert ok.status_code == 200
    assert len(ok.json()) == 1
