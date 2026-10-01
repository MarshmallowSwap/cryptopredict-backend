"""Real ASGI HTTP tests + SDK-independent query spies; no external services."""
import asyncio
import hashlib
import hmac
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

# These values are inert test data, never credentials for an external project.
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "local-test-only")
os.environ.setdefault("RECOVERY_ADMIN_TOKEN", "")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient
from app.core.recovery import RecoveryGuard, RecoveryWriteDisabled, MODE
from app.core.readonly_db import ReadOnlySupabase

TOKEN = "T" * 64
PRIVATE = "/api/v1/users/00000000-0000-0000-0000-000000000001"
PUBLIC = "/api/v1/markets/00000000-0000-0000-0000-000000000001"


def make_client(token=TOKEN):
    calls = Mock()
    api = FastAPI()

    @api.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"])
    async def handler(path: str):
        calls(path)
        return {"ok": True}

    api.add_middleware(RecoveryGuard, admin_token=token)
    api.add_middleware(CORSMiddleware, allow_origins=["https://ui.example"],
                       allow_methods=["GET", "HEAD", "OPTIONS"], allow_headers=["Authorization"])
    return TestClient(api), calls


class HttpRecoveryTests(unittest.TestCase):
    def test_mutation_matrix_cannot_reach_handler(self):
        for method in ("POST", "PUT", "PATCH", "DELETE", "TRACE"):
            for path in ("/api/v1/users/u/deposit", "/api/v1/markets/m/bet", "/api/v1/markets/m/resolve",
                         "/api/v1/yield/accrue", "/api/v1/admin/cron/resolve-expired", "/api/v1/markets/upload/image",
                         "/api/v1/admin/markets/m/cancel", "/future/route"):
                with self.subTest(method=method, path=path):
                    client, calls = make_client()
                    response = client.request(method, path, content=b"not-even-valid-json",
                                              headers={"Authorization": f"Bearer {TOKEN}"})
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["code"], "RECOVERY_READ_ONLY")
                    calls.assert_not_called()

    def test_body_is_not_consumed_on_denial(self):
        async def execute():
            downstream = Mock()
            guard = RecoveryGuard(downstream)
            received = Mock(side_effect=AssertionError("Request body consumed"))
            messages = []
            async def send(message):
                messages.append(message)
            await guard({"type": "http", "method": "POST", "path": "/any", "headers": []}, received, send)
            received.assert_not_called()
            downstream.assert_not_called()
            self.assertEqual(messages[0]["status"], 503)
        asyncio.run(execute())

    def test_public_reads(self):
        for path in ("/", "/health", "/api/v1/system/status", "/api/v1/markets",
                     "/api/v1/markets/", "/api/v1/markets/images/all", PUBLIC,
                     "/api/v1/yield/stats", PUBLIC.replace("/markets/", "/yield/market/")):
            with self.subTest(path=path):
                client, calls = make_client("")
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["x-cryptopredict-mode"], MODE)
                self.assertEqual(response.headers["cache-control"], "no-store")
                calls.assert_called_once()

    def test_private_and_future_reads_are_closed_by_default(self):
        for path in (PRIVATE, "/api/v1/admin/stats", "/api/v1/positions", "/openapi.json",
                     "/api/v1/markets/new-sensitive-route", "/future"):
            with self.subTest(path=path):
                client, calls = make_client()
                self.assertEqual(client.get(path).status_code, 401)
                calls.assert_not_called()

    def test_unconfigured_admin_fails_closed(self):
        client, calls = make_client("")
        self.assertEqual(client.get(PRIVATE, headers={"Authorization": "Bearer "}).status_code, 503)
        calls.assert_not_called()

    def test_invalid_authentication(self):
        for authorization in ("", "Basic " + TOKEN, "Bearer wrong", "Bearer " + TOKEN + " ", "Bearer " + "X" * 300):
            with self.subTest(authorization_length=len(authorization)):
                client, calls = make_client()
                self.assertEqual(client.get(PRIVATE, headers={"Authorization": authorization}).status_code, 401)
                calls.assert_not_called()

    def test_duplicate_authorization_is_rejected(self):
        client, calls = make_client()
        response = client.get(PRIVATE, headers=[("Authorization", "Bearer " + TOKEN), ("Authorization", "Bearer " + TOKEN)])
        self.assertEqual(response.status_code, 401)
        calls.assert_not_called()

    def test_valid_header_allows_private_read_not_write(self):
        client, calls = make_client()
        self.assertEqual(client.get(PRIVATE, headers={"Authorization": "Bearer " + TOKEN}).status_code, 200)
        calls.assert_called_once()

    def test_credentials_in_urls_rejected_even_with_valid_header(self):
        for query in ("admin_token=x", "admin_token=", "access_token=x", "admin%5ftoken=x"):
            with self.subTest(query=query):
                client, calls = make_client()
                response = client.get("/health?" + query, headers={"Authorization": "Bearer " + TOKEN})
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(TOKEN, response.text)
                calls.assert_not_called()

    def test_cors_preflight_for_write_denied(self):
        client, calls = make_client()
        response = client.options("/api/v1/markets", headers={"Origin": "https://ui.example", "Access-Control-Request-Method": "POST"})
        self.assertEqual(response.status_code, 400)
        calls.assert_not_called()

    def test_cors_read_preflight_and_nonpreflight_have_no_side_effect(self):
        client, calls = make_client()
        response = client.options(PRIVATE, headers={"Origin": "https://ui.example", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "Authorization"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.options("/any").status_code, 204)
        calls.assert_not_called()

    def test_head_needs_authorization(self):
        client, calls = make_client()
        self.assertEqual(client.head(PRIVATE).status_code, 401)
        calls.assert_not_called()

    def test_websocket_denied(self):
        async def execute():
            called = Mock()
            guard = RecoveryGuard(called)
            messages = []
            async def send(message):
                messages.append(message)
            await guard({"type": "websocket"}, Mock(), send)
            called.assert_not_called()
            self.assertEqual(messages, [{"type": "websocket.close", "code": 1008}])
        asyncio.run(execute())


class ReadOnlyDatabaseTests(unittest.TestCase):
    def test_select_preserves_results(self):
        sdk = Mock()
        sdk.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = {"data": []}
        result = ReadOnlySupabase(sdk).table("markets").select("id").eq("status", "open").order("id").limit(10).execute()
        self.assertEqual(result, {"data": []})
        sdk.table.assert_called_once_with("markets")

    def test_table_mutation_never_reaches_sdk(self):
        for name in ("insert", "update", "upsert", "delete", "execute"):
            with self.subTest(name=name):
                sdk = Mock()
                table = ReadOnlySupabase(sdk).table("users")
                with self.assertRaises(RecoveryWriteDisabled):
                    getattr(table, name)
                sdk.table.assert_not_called()

    def test_client_mutation_or_raw_access_blocked(self):
        for name in ("rpc", "storage", "auth", "postgrest", "schema", "from_"):
            with self.subTest(name=name):
                sdk = Mock()
                with self.assertRaises(RecoveryWriteDisabled):
                    getattr(ReadOnlySupabase(sdk), name)
                self.assertEqual(sdk.mock_calls, [])

    def test_query_cannot_be_switched_to_write(self):
        for name in ("insert", "update", "delete", "upsert", "rpc"):
            with self.subTest(name=name):
                sdk = Mock()
                query = ReadOnlySupabase(sdk).table("users").select("id")
                sdk.reset_mock()
                with self.assertRaises(RecoveryWriteDisabled):
                    getattr(query, name)
                self.assertEqual(sdk.mock_calls, [])

    def test_negated_filter_and_single_are_supported(self):
        sdk = Mock()
        sdk.table.return_value.select.return_value.not_.is_.return_value.single.return_value.execute.return_value = "ok"
        self.assertEqual(ReadOnlySupabase(sdk).table("markets").select("*").not_.is_("image_url", "null").single().execute(), "ok")


class JobQuarantineTests(unittest.TestCase):
    def test_resolver_no_longer_needs_web3_or_a_signing_key(self):
        from app.services.auto_resolver import run_auto_resolver, resolve_tx, auto_resolve_price_market
        self.assertEqual(asyncio.run(run_auto_resolver())["resolved"], 0)
        for coroutine in (resolve_tx(None, None, None, 1, True), auto_resolve_price_market(None, None, None, {})):
            with self.assertRaises(RecoveryWriteDisabled):
                asyncio.run(coroutine)

    def test_yield_cannot_mutate_even_when_called_directly(self):
        from app.services.yield_engine import accrue_daily_yield, distribute_staking_yield
        sb = Mock()
        for coroutine in (accrue_daily_yield(), distribute_staking_yield(sb, 100.0)):
            with self.assertRaises(RecoveryWriteDisabled):
                asyncio.run(coroutine)
        self.assertEqual(sb.mock_calls, [])

    def test_estimates_explicitly_nonredeemable(self):
        from app.services.yield_engine import compute_market_yield
        result = compute_market_yield(1000, 365)
        self.assertEqual(result["total_yield_estimated"], 48)
        self.assertFalse(result["redeemable"])
        self.assertFalse(result["funding_verified"])
        self.assertEqual(compute_market_yield(1000, -1)["total_yield_estimated"], 0)

    def test_start_has_no_scheduler_or_signing_imports(self):
        import ast
        tree = ast.parse((Path(__file__).parents[1] / "start.py").read_text())
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imports, {"app.main"})
        self.assertNotIn("scheduler", (Path(__file__).parents[1] / "start.py").read_text().split('"""')[-1])


class SettingsTests(unittest.TestCase):
    def test_empty_legacy_tokens_have_no_defaults(self):
        from app.core.config import Settings
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None, SUPABASE_URL="https://example.invalid", SUPABASE_SERVICE_KEY="test")
        self.assertEqual(settings.ADMIN_TOKEN, "")
        self.assertEqual(settings.RECOVERY_ADMIN_TOKEN, "")

    def test_short_or_historical_recovery_tokens_rejected(self):
        from app.core.config import Settings
        from pydantic import ValidationError
        for token in ("short", "cp-admin-" + "a" * 60, "a" * 47, "x " * 32):
            with self.subTest(token_length=len(token)):
                with self.assertRaises(ValidationError) as err:
                    Settings(_env_file=None, SUPABASE_URL="https://example.invalid", SUPABASE_SERVICE_KEY="test", RECOVERY_ADMIN_TOKEN=token)
                self.assertNotIn(token, str(err.exception))

    def test_fresh_token_valid_and_not_in_repr(self):
        from app.core.config import Settings
        settings = Settings(_env_file=None, SUPABASE_URL="https://example.invalid", SUPABASE_SERVICE_KEY="test", RECOVERY_ADMIN_TOKEN=TOKEN)
        self.assertEqual(settings.RECOVERY_ADMIN_TOKEN, TOKEN)
        self.assertNotIn(TOKEN, repr(settings))


class WebhookTests(unittest.TestCase):
    def test_missing_secret_fails_closed(self):
        import webhook
        with patch.object(webhook, "WEBHOOK_SECRET", ""):
            self.assertEqual(TestClient(webhook.app).post("/webhook/github", content=b"{}").status_code, 503)
            self.assertFalse(webhook.verify_signature(b"{}", "sha256=" + "a" * 64))

    def test_bad_signature_denied(self):
        import webhook
        with patch.object(webhook, "WEBHOOK_SECRET", TOKEN):
            self.assertEqual(TestClient(webhook.app).post("/webhook/github", content=b"{}", headers={"X-Hub-Signature-256": "sha256=" + "0" * 64}).status_code, 401)

    def test_valid_main_push_still_does_not_deploy(self):
        import webhook
        body = b'{"ref":"refs/heads/main"}'
        signature = "sha256=" + hmac.new(TOKEN.encode(), body, hashlib.sha256).hexdigest()
        with patch.object(webhook, "WEBHOOK_SECRET", TOKEN), patch("subprocess.run") as run:
            response = TestClient(webhook.app).post("/webhook/github", content=body, headers={"X-Hub-Signature-256": signature, "X-GitHub-Event": "push"})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["status"], "deployment_disabled")
            run.assert_not_called()

    def test_payload_size_limit(self):
        import webhook
        with patch.object(webhook, "WEBHOOK_SECRET", TOKEN):
            self.assertEqual(TestClient(webhook.app).post("/webhook/github", content=b"x" * 1_048_577).status_code, 413)


class RealReadRouteTests(unittest.TestCase):
    def test_admin_read_uses_new_header_and_preserves_aggregates(self):
        from types import SimpleNamespace
        from app.routers import admin
        sdk = Mock()
        sdk.table.return_value.select.return_value.execute.side_effect = [
            SimpleNamespace(data=[{"status": "open"}, {"status": "open"}], count=2),
            SimpleNamespace(data=[], count=3),
            SimpleNamespace(data=[{"stake": 12.5}], count=1),
        ]
        api = FastAPI()
        api.state.recovery_admin_token = TOKEN
        api.include_router(admin.router, prefix="/api/v1/admin")
        api.add_middleware(RecoveryGuard, admin_token=TOKEN)
        with patch.object(admin, "get_supabase", return_value=ReadOnlySupabase(sdk)):
            client = TestClient(api)
            self.assertEqual(client.get("/api/v1/admin/stats").status_code, 401)
            sdk.table.assert_not_called()
            response = client.get("/api/v1/admin/stats", headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["markets_by_status"], {"open": 2})
        self.assertEqual(response.json()["total_users"], 3)
        self.assertEqual(response.json()["total_volume"], 12.5)
        self.assertFalse(response.json()["redeemable"])

    def test_yield_missing_market_is_404_not_name_error(self):
        from app.services import yield_engine as module
        sb = Mock()
        sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = None
        with patch.object(module, "get_supabase", return_value=sb):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as err:
                asyncio.run(module.market_yield("missing"))
            self.assertEqual(err.exception.status_code, 404)

    def test_yield_timestamps_handle_naive_utc_and_offsets(self):
        from datetime import datetime, timezone, timedelta
        from app.services import yield_engine as module
        future = datetime.now(timezone.utc) + timedelta(days=3, hours=1)
        for timestamp in (future.isoformat(), future.replace(tzinfo=None).isoformat(),
                          future.astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat()):
            with self.subTest(timestamp=timestamp):
                sb = Mock()
                sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
                    "expires_at": timestamp, "pool_size": 1000}
                with patch.object(module, "get_supabase", return_value=sb):
                    result = asyncio.run(module.market_yield("test"))
                self.assertEqual(result["days_remaining"], 3)
                self.assertFalse(result["redeemable"])


if __name__ == "__main__":
    unittest.main()
