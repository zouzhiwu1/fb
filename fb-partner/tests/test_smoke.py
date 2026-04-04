# -*- coding: utf-8 -*-
from unittest import mock

import pytest


def _patched_board_commission(commission: float):
    def _inner(agent, ym):
        from app.dashboard import build_monthly_board_dict as _real

        r = _real(agent, ym)
        s = dict(r.get("summary") or {})
        s["commission_yuan"] = commission
        r["summary"] = s
        return r

    return _inner


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv(
        "PARTNER_JWT_SECRET_KEY",
        "unit-test-partner-jwt-secret-key-32bytes!",
    )
    monkeypatch.setenv("PARTNER_BOOTSTRAP_KEY", "unit-test-bootstrap-key")
    monkeypatch.setenv("PARTNER_ROOT_PASSWORD", "unit-test-root-pw")
    monkeypatch.setenv("PARTNER_ROOT_SESSION_VERSION", "1")
    monkeypatch.delenv("PARTNER_INITIAL_ADMINS_JSON", raising=False)
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def test_login_page(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "代理商" in r.get_data(as_text=True)


def test_dashboard_page(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert "明细看板" in text
    assert "推广二维码" in text


def test_partner_promo_page(client):
    r = client.get("/promo")
    assert r.status_code == 200
    t = r.get_data(as_text=True)
    assert "推广二维码" in t and "promo_cards" in t


def test_monthly_board_requires_auth(client):
    r = client.get("/api/partner/stats/monthly-board")
    assert r.status_code == 401


def test_monthly_board_ok_for_agent(client):
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    client.post(
        "/api/partner/auth/bootstrap-agent",
        json={
            "login_name": "dash_ag@test.local",
            "password": "Dash1!dashpw",
            "agent_code": "DASH01",
            "display_name": "看板测",
        },
        headers=h,
    )
    r1 = client.post(
        "/api/partner/auth/login",
        json={"login_name": "dash_ag@test.local", "password": "Dash1!dashpw"},
    )
    assert r1.status_code == 200
    token = r1.get_json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    r2 = client.get("/api/partner/stats/monthly-board?month=2026-01", headers=auth)
    assert r2.status_code == 200
    body = r2.get_json()
    assert body.get("ok") is True
    assert body.get("month") == "2026-01"
    assert "summary" in body
    assert body["summary"].get("settled_commission_yuan") == 0.0
    assert isinstance(body.get("referrals"), list)
    assert isinstance(body.get("recharges"), list)


def test_partner_account_page(client):
    r = client.get("/account")
    assert r.status_code == 200
    assert "账户管理" in r.get_data(as_text=True)


def test_partner_put_me_profile_and_password(client):
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    client.post(
        "/api/partner/auth/bootstrap-agent",
        json={
            "login_name": "acc_ag@test.local",
            "password": "orig-pw-12",
            "agent_code": "ACC01",
            "display_name": "账户测",
            "phone": "13600001111",
        },
        headers=h,
    )
    r1 = client.post(
        "/api/partner/auth/login",
        json={"login_name": "acc_ag@test.local", "password": "orig-pw-12"},
    )
    assert r1.status_code == 200
    tok = r1.get_json()["token"]
    hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    bad = client.put(
        "/api/partner/auth/me",
        json={"current_password": "wrong", "new_password": "new-pass-99"},
        headers=hdr,
    )
    assert bad.status_code == 400

    client.post(
        "/api/partner/auth/bootstrap-agent",
        json={
            "login_name": "acc_ag2@test.local",
            "password": "other-pw-12",
            "agent_code": "ACC02",
            "phone": "13600002222",
        },
        headers=h,
    )
    conflict = client.put(
        "/api/partner/auth/me",
        json={"phone": "13600002222"},
        headers=hdr,
    )
    assert conflict.status_code == 400

    ok = client.put(
        "/api/partner/auth/me",
        json={
            "display_name": "新显示名",
            "real_name": "王五",
            "payout_channel": "alipay",
            "payout_account": "13600003333",
            "payout_holder_name": "王五",
            "phone": "13600003333",
        },
        headers=hdr,
    )
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["agent"]["display_name"] == "新显示名"
    assert body.get("token") is None

    ok_pw = client.put(
        "/api/partner/auth/me",
        json={"current_password": "orig-pw-12", "new_password": "changed-99"},
        headers=hdr,
    )
    assert ok_pw.status_code == 200
    new_tok = ok_pw.get_json().get("token")
    assert new_tok

    assert client.get("/api/partner/auth/me", headers=hdr).status_code == 401

    new_hdr = {"Authorization": f"Bearer {new_tok}", "Content-Type": "application/json"}
    assert client.get("/api/partner/auth/me", headers=new_hdr).status_code == 200

    r_login = client.post(
        "/api/partner/auth/login",
        json={"login_name": "acc_ag@test.local", "password": "changed-99"},
    )
    assert r_login.status_code == 200


def test_partner_promo_links(client, monkeypatch):
    monkeypatch.setenv(
        "PARTNER_PROMO_MP_QR_TARGET",
        "https://h5.example.com/mp?aid={agent_id}&code={agent_code}",
    )
    monkeypatch.setenv(
        "PARTNER_PROMO_ANDROID_URL",
        "https://dl.example.com/app.apk?ref={agent_id}",
    )
    monkeypatch.setenv(
        "PARTNER_PROMO_WEB_URL",
        "https://h5.example.com/register?ref={agent_id}&code={agent_code}",
    )
    monkeypatch.setenv(
        "PARTNER_PROMO_IOS_URL",
        "https://apps.apple.com/app/id1?c={agent_code}",
    )
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    client.post(
        "/api/partner/auth/bootstrap-agent",
        json={
            "login_name": "promo_ag@test.local",
            "password": "promo-pw-99",
            "agent_code": "PROMO1",
            "display_name": "推广测",
        },
        headers=h,
    )
    r1 = client.post(
        "/api/partner/auth/login",
        json={"login_name": "promo_ag@test.local", "password": "promo-pw-99"},
    )
    tok = r1.get_json()["token"]
    r2 = client.get(
        "/api/partner/stats/promo-links",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r2.status_code == 200
    body = r2.get_json()
    assert body.get("ok") is True
    assert body.get("agent_code") == "PROMO1"
    aid = str(body.get("agent_id"))
    ch = {c["id"]: c for c in body["channels"]}
    assert "miniprogram" in ch and ch["miniprogram"]["qr_url"].startswith("https://h5.example.com/mp?")
    assert aid in ch["miniprogram"]["qr_url"] and "PROMO1" in ch["miniprogram"]["qr_url"]
    assert "web" in ch and ch["web"]["qr_url"].startswith("https://h5.example.com/register?")
    assert aid in ch["web"]["qr_url"] and "PROMO1" in ch["web"]["qr_url"]
    assert ch["android"]["qr_url"].startswith("https://dl.example.com/") and aid in ch["android"]["qr_url"]
    assert "PROMO1" in ch["ios"]["qr_url"]
    assert ch["miniprogram"].get("wechat_scene")
    assert "agent_id=" in ch["miniprogram"].get("miniprogram_path", "")


def test_home_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "管理员登录" in r.get_data(as_text=True)


def test_admin_login_page(client):
    r = client.get("/admin/login")
    assert r.status_code == 200
    assert "管理员" in r.get_data(as_text=True)


def test_admin_root_redirects_to_agents_list(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/agents" in (r.headers.get("Location") or "")


def test_admin_agents_pages_have_ui(client):
    r = client.get("/admin/agents")
    assert r.status_code == 200
    t = r.get_data(as_text=True)
    assert "代理商一览" in t and "查看" in t and "修改" in t and "服务费" in t
    r2 = client.get("/admin/agents/new")
    assert r2.status_code == 200
    assert "注册代理商" in r2.get_data(as_text=True)


def test_admin_agents_requires_auth(client):
    r = client.get("/api/partner/admin/agents")
    assert r.status_code == 401


def test_admin_agent_monthly_board_api(client, app):
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    client.post(
        "/api/partner/auth/bootstrap-admin",
        json={"login_name": "adm_board", "password": "Adm1!passbd"},
        headers=h,
    )
    r1 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "adm_board", "password": "Adm1!passbd"},
    )
    token = r1.get_json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    r2 = client.post(
        "/api/partner/admin/agents",
        json={
            "login_name": "ag_board@test.local",
            "password": "Pw1!bdbdbd",
            "agent_code": "BD01",
            "real_name": "看板代查",
            "age": 30,
            "phone": "13611112222",
            "payout_channel": "alipay",
            "payout_account": "13611112222",
            "payout_holder_name": "看板代查",
        },
        headers={**auth, "Content-Type": "application/json"},
    )
    assert r2.status_code == 200
    aid = r2.get_json()["agent"]["id"]
    r3 = client.get(
        f"/api/partner/admin/agents/{aid}/monthly-board?month=2026-03",
        headers=auth,
    )
    assert r3.status_code == 200
    body = r3.get_json()
    assert body.get("ok") is True
    assert body.get("month") == "2026-03"
    assert "summary" in body
    r4 = client.get("/admin/agents/%s/commission" % aid)
    assert r4.status_code == 200
    t4 = r4.get_data(as_text=True)
    assert "服务费" in t4 and "结算服务费" in t4

    r5 = client.get("/admin/agents/%s/dashboard" % aid, follow_redirects=False)
    assert r5.status_code == 302
    assert "/commission" in (r5.headers.get("Location") or "")

    r5b = client.post(
        f"/api/partner/admin/agents/{aid}/commission/settle",
        json={
            "amount_yuan": "1",
            "settlement_month": "2026-03",
            "payment_channel": "alipay",
            "payment_reference": "UNIT-R5B",
        },
        headers={**auth, "Content-Type": "application/json"},
    )
    assert r5b.status_code == 400
    assert "待付" in (r5b.get_json().get("message") or "")

    with mock.patch(
        "app.admin_api.build_monthly_board_dict",
        _patched_board_commission(100.0),
    ):
        r6 = client.post(
            f"/api/partner/admin/agents/{aid}/commission/settle",
            json={
                "amount_yuan": "88.5",
                "settlement_month": "2026-03",
                "payment_channel": "alipay",
                "payment_reference": "UNIT-TEST-ORDER-885",
                "payment_note": "pytest settle",
            },
            headers={**auth, "Content-Type": "application/json"},
        )
    assert r6.status_code == 200
    j6 = r6.get_json()
    assert j6.get("ok") is True
    assert j6.get("settled_commission_yuan") == 88.5
    assert j6.get("settlement_month") == "2026-03"
    assert j6.get("settlement_id")
    from app.models import AgentCommissionSettlement, PartnerAdmin

    with app.app_context():
        adm = PartnerAdmin.query.filter_by(login_name="adm_board").first()
        row = AgentCommissionSettlement.query.filter_by(agent_id=aid).order_by(
            AgentCommissionSettlement.id.desc()
        ).first()
        assert row is not None
        assert row.partner_admin_id == adm.id
        assert row.settlement_month == "2026-03"
        assert float(row.amount_yuan) == 88.5
        assert row.payment_channel == "alipay"
        assert row.payment_reference == "UNIT-TEST-ORDER-885"
        assert (row.payment_note or "") == "pytest settle"

    r7 = client.get(
        f"/api/partner/admin/agents/{aid}/monthly-board?month=2026-03",
        headers=auth,
    )
    assert r7.get_json()["summary"].get("settled_commission_yuan") == 88.5

    with mock.patch(
        "app.admin_api.build_monthly_board_dict",
        _patched_board_commission(100.0),
    ):
        r8 = client.post(
            f"/api/partner/admin/agents/{aid}/commission/settle",
            json={
                "amount_yuan": "20",
                "settlement_month": "2026-03",
                "payment_channel": "wechat",
                "payment_reference": "UNIT-R8",
            },
            headers={**auth, "Content-Type": "application/json"},
        )
    assert r8.status_code == 400
    j8 = r8.get_json()
    assert j8.get("pending_commission_yuan") == 11.5


def test_admin_register_agent_flow(client):
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    r0 = client.post(
        "/api/partner/auth/bootstrap-admin",
        json={"login_name": "adm1", "password": "adm-pass-1"},
        headers=h,
    )
    assert r0.status_code == 200 and r0.get_json()["ok"] is True
    r1 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "adm1", "password": "adm-pass-1"},
    )
    assert r1.status_code == 200
    token = r1.get_json()["token"]
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r2 = client.post(
        "/api/partner/admin/agents",
        json={
            "login_name": "ag1@test.local",
            "password": "ag-pass-1",
            "agent_code": "T001",
            "real_name": "张三",
            "age": 30,
            "phone": "13800138000",
            "payout_channel": "wechat",
            "payout_account": "wx_zhangsan",
            "payout_holder_name": "张三",
            "current_rate": 0.08,
        },
        headers=auth,
    )
    assert r2.status_code == 200 and r2.get_json()["ok"] is True
    r3 = client.post(
        "/api/partner/auth/login",
        json={"login_name": "ag1@test.local", "password": "ag-pass-1"},
    )
    assert r3.status_code == 200 and r3.get_json()["ok"] is True


def test_admin_agent_code_unique_case_insensitive(client):
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    client.post(
        "/api/partner/auth/bootstrap-admin",
        json={"login_name": "adm_uq", "password": "Adm1!passuq"},
        headers=h,
    )
    r1 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "adm_uq", "password": "Adm1!passuq"},
    )
    token = r1.get_json()["token"]
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    ok = client.post(
        "/api/partner/admin/agents",
        json={
            "login_name": "uq_ag_a@test.local",
            "password": "pw-uu-11",
            "agent_code": "UniqueCODE",
            "real_name": "甲",
            "age": 20,
            "phone": "13100000001",
            "payout_channel": "alipay",
            "payout_account": "13100000001",
            "payout_holder_name": "甲",
        },
        headers=auth,
    )
    assert ok.status_code == 200
    r_dup = client.post(
        "/api/partner/admin/agents",
        json={
            "login_name": "uq_ag_b@test.local",
            "password": "pw-uu-22",
            "agent_code": "uniquecode",
            "real_name": "乙",
            "age": 21,
            "phone": "13100000002",
            "payout_channel": "alipay",
            "payout_account": "13100000002",
            "payout_holder_name": "乙",
        },
        headers=auth,
    )
    assert r_dup.status_code == 400
    assert "推广码" in r_dup.get_json().get("message", "")


def test_admin_check_agent_code_endpoint(client):
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    client.post(
        "/api/partner/auth/bootstrap-admin",
        json={"login_name": "adm_ck", "password": "Adm1!passck"},
        headers=h,
    )
    r1 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "adm_ck", "password": "Adm1!passck"},
    )
    token = r1.get_json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/partner/admin/agents/check-agent-code", headers=auth).status_code == 400

    auth_json = {**auth, "Content-Type": "application/json"}
    cr = client.post(
        "/api/partner/admin/agents",
        json={
            "login_name": "ck_ag@test.local",
            "password": "Pw1!ckagent",
            "agent_code": "CkCode99",
            "real_name": "丙",
            "age": 22,
            "phone": "13100000003",
            "payout_channel": "wechat",
            "payout_account": "wx_ck",
            "payout_holder_name": "丙",
        },
        headers=auth_json,
    )
    assert cr.status_code == 200
    aid = cr.get_json()["agent"]["id"]

    c1 = client.get(
        "/api/partner/admin/agents/check-agent-code?code=ckcode99",
        headers=auth,
    )
    assert c1.status_code == 200 and c1.get_json()["available"] is False

    c2 = client.get(
        "/api/partner/admin/agents/check-agent-code?code=BRAND_NEW_XX",
        headers=auth,
    )
    assert c2.status_code == 200 and c2.get_json()["available"] is True

    c3 = client.get(
        f"/api/partner/admin/agents/check-agent-code?code=ckcode99&exclude_id={aid}",
        headers=auth,
    )
    assert c3.status_code == 200 and c3.get_json()["available"] is True


def test_admin_get_put_agent(client):
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    client.post(
        "/api/partner/auth/bootstrap-admin",
        json={"login_name": "adm2", "password": "adm-pass-2"},
        headers=h,
    )
    r1 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "adm2", "password": "adm-pass-2"},
    )
    token = r1.get_json()["token"]
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r2 = client.post(
        "/api/partner/admin/agents",
        json={
            "login_name": "ag2@test.local",
            "password": "Pw2!agtwoo",
            "agent_code": "T002",
            "real_name": "李四",
            "age": 40,
            "phone": "13900139000",
            "payout_channel": "alipay",
            "payout_account": "13900139000",
            "payout_holder_name": "李四",
        },
        headers=auth,
    )
    assert r2.status_code == 200
    aid = r2.get_json()["agent"]["id"]
    rg = client.get(f"/api/partner/admin/agents/{aid}", headers=auth)
    assert rg.status_code == 200 and rg.get_json()["agent"]["login_name"] == "ag2@test.local"
    ru = client.put(
        f"/api/partner/admin/agents/{aid}",
        json={
            "real_name": "李四改",
            "age": 41,
            "phone": "13900139000",
            "payout_channel": "alipay",
            "payout_account": "13900139000",
            "payout_holder_name": "李四改",
            "login_name": "ag2@test.local",
            "agent_code": "T002",
            "display_name": "李四改",
            "current_rate": 0.1,
            "status": "active",
        },
        headers=auth,
    )
    assert ru.status_code == 200 and ru.get_json()["agent"]["real_name"] == "李四改"
    rp = client.put(
        f"/api/partner/admin/agents/{aid}",
        json={
            "login_name": "ag2@test.local",
            "agent_code": "T002",
            "real_name": "李四改",
            "age": 41,
            "phone": "13900139000",
            "payout_channel": "alipay",
            "payout_account": "13900139000",
            "payout_holder_name": "李四改",
            "password": "New1!secretpw",
            "status": "disabled",
        },
        headers=auth,
    )
    assert rp.status_code == 200
    r_login = client.post(
        "/api/partner/auth/login",
        json={"login_name": "ag2@test.local", "password": "New1!secretpw"},
    )
    assert r_login.status_code == 403
    client.put(
        f"/api/partner/admin/agents/{aid}",
        json={"status": "active"},
        headers=auth,
    )
    r_ok = client.post(
        "/api/partner/auth/login",
        json={"login_name": "ag2@test.local", "password": "New1!secretpw"},
    )
    assert r_ok.status_code == 200 and r_ok.get_json().get("ok") is True


def test_admin_delete_agent_disabled(client):
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    client.post(
        "/api/partner/auth/bootstrap-admin",
        json={"login_name": "adm_del", "password": "Adm1!passdel"},
        headers=h,
    )
    r1 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "adm_del", "password": "Adm1!passdel"},
    )
    token = r1.get_json()["token"]
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r2 = client.post(
        "/api/partner/admin/agents",
        json={
            "login_name": "ag_del@test.local",
            "password": "Pw1!delag01",
            "agent_code": "DEL01",
            "real_name": "保留",
            "age": 20,
            "phone": "13700000001",
            "payout_channel": "alipay",
            "payout_account": "13700000001",
            "payout_holder_name": "保留",
        },
        headers=auth,
    )
    assert r2.status_code == 200
    aid = r2.get_json()["agent"]["id"]
    rd = client.delete(f"/api/partner/admin/agents/{aid}", headers=auth)
    assert rd.status_code == 405
    rg = client.get(f"/api/partner/admin/agents/{aid}", headers=auth)
    assert rg.status_code == 200 and rg.get_json().get("ok") is True


def test_root_login_and_whoami(client):
    r = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "root", "password": "unit-test-root-pw"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("ok") is True
    assert body.get("token")
    assert body.get("admin", {}).get("role") == "root"
    token = body["token"]
    r2 = client.get(
        "/api/partner/auth/admin/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    j2 = r2.get_json()
    assert j2.get("role") == "root"


def test_root_cannot_list_agents_api(client):
    r = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "root", "password": "unit-test-root-pw"},
    )
    token = r.get_json()["token"]
    r2 = client.get(
        "/api/partner/admin/agents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 403


def test_root_creates_admin_and_admin_lists_agents(client):
    r0 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "root", "password": "unit-test-root-pw"},
    )
    root_tok = r0.get_json()["token"]
    r1 = client.post(
        "/api/partner/admin/admins",
        json={"login_name": "ops_smoke", "password": "ops-pass-12"},
        headers={
            "Authorization": f"Bearer {root_tok}",
            "Content-Type": "application/json",
        },
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "ops_smoke", "password": "ops-pass-12"},
    )
    assert r2.status_code == 200
    adm_tok = r2.get_json()["token"]
    r3 = client.get(
        "/api/partner/admin/agents",
        headers={"Authorization": f"Bearer {adm_tok}"},
    )
    assert r3.status_code == 200
    assert r3.get_json().get("ok") is True


def test_bootstrap_admin_rejects_reserved_root_login(client):
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    r = client.post(
        "/api/partner/auth/bootstrap-admin",
        json={"login_name": "root", "password": "pw-123456"},
        headers=h,
    )
    assert r.status_code == 400


def test_db_admin_cannot_manage_admins_api(client):
    h = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}
    client.post(
        "/api/partner/auth/bootstrap-admin",
        json={"login_name": "adm_only", "password": "adm-only-pw-1"},
        headers=h,
    )
    r1 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "adm_only", "password": "adm-only-pw-1"},
    )
    tok = r1.get_json()["token"]
    r2 = client.get(
        "/api/partner/admin/admins",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r2.status_code == 403


def test_root_crud_partner_admins(client):
    r0 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "root", "password": "unit-test-root-pw"},
    )
    assert r0.status_code == 200
    root_tok = r0.get_json()["token"]
    h = {"Authorization": f"Bearer {root_tok}", "Content-Type": "application/json"}
    r1 = client.post(
        "/api/partner/admin/admins",
        json={"login_name": "crud_a", "password": "pw-crud-12"},
        headers=h,
    )
    assert r1.status_code == 200
    id_a = r1.get_json()["admin"]["id"]
    r2 = client.post(
        "/api/partner/admin/admins",
        json={"login_name": "crud_b", "password": "pw-crud-34"},
        headers=h,
    )
    assert r2.status_code == 200
    id_b = r2.get_json()["admin"]["id"]
    r3 = client.put(
        f"/api/partner/admin/admins/{id_a}",
        json={"login_name": "crud_a2", "status": "disabled"},
        headers=h,
    )
    assert r3.status_code == 200
    assert r3.get_json()["admin"]["login_name"] == "crud_a2"
    assert r3.get_json()["admin"]["status"] == "disabled"
    r4 = client.delete(f"/api/partner/admin/admins/{id_a}", headers=h)
    assert r4.status_code == 200
    r5 = client.delete(f"/api/partner/admin/admins/{id_b}", headers=h)
    assert r5.status_code == 400


def test_create_partner_admin_rejects_reserved_root_login(client):
    r0 = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "root", "password": "unit-test-root-pw"},
    )
    root_tok = r0.get_json()["token"]
    r1 = client.post(
        "/api/partner/admin/admins",
        json={"login_name": "root", "password": "some-pass-12"},
        headers={
            "Authorization": f"Bearer {root_tok}",
            "Content-Type": "application/json",
        },
    )
    assert r1.status_code == 400
