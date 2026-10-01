"""Native FastAPI integration tests; fake RPC, no network or database calls."""
import os
os.environ.setdefault('SUPABASE_URL', 'https://example.invalid')
os.environ.setdefault('SUPABASE_SERVICE_KEY', 'not-a-real-test-key')

import threading
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from app.core.recovery import RecoveryGuard
from app.routers import markets
from app.services.chain_catalog import Catalog, MARKET
from test_chain_catalog import FakeRPC, NOW

TOKEN = 'test_' + 'a' * 60


class NativeMarketsTests(unittest.TestCase):
    def setUp(self):
        self.rpc = FakeRPC()
        self.catalog = Catalog(self.rpc, clock=lambda: NOW)
        self.patch = patch.object(markets, '_catalog', self.catalog)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        app = FastAPI()
        app.add_middleware(RecoveryGuard, admin_token=TOKEN)
        app.add_middleware(CORSMiddleware, allow_origins=['https://cryptopredict.app'],
                           allow_credentials=False, allow_methods=['GET', 'HEAD', 'OPTIONS'],
                           allow_headers=['Authorization', 'Content-Type'])
        app.include_router(markets.router, prefix='/api/v1/markets')
        app.include_router(markets.canonical_router, prefix='/api/v1/recovery/markets')
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_original_route_returns_real_catalog_shape(self):
        r = self.client.get('/api/v1/markets')
        self.assertEqual(r.status_code, 200)
        x = r.json()
        self.assertEqual(x['source'], 'base-sepolia-rpc')
        self.assertEqual(x['total'], 3)
        self.assertTrue(x['complete'])
        self.assertEqual(x['contract_address'], MARKET)
        self.assertFalse(x['database_used'])
        self.assertFalse(x['transaction_actions_enabled'])

    def test_alias_uses_identical_snapshot_and_cache(self):
        a = self.client.get('/api/v1/markets').json()
        calls = len(self.rpc.calls)
        b = self.client.get('/api/v1/recovery/markets').json()
        self.assertEqual(len(self.rpc.calls), calls)
        self.assertEqual(a['snapshot_digest'], b['snapshot_digest'])
        self.assertEqual(a['markets'], b['markets'])

    def test_original_numeric_detail(self):
        r = self.client.get('/api/v1/markets/2')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['market']['outcome'], 'NO')
        self.assertNotIn('markets', r.json())

    def test_canonical_detail(self):
        r = self.client.get('/api/v1/recovery/markets/2')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['market']['id'], '2')

    def test_not_found(self):
        self.assertEqual(self.client.get('/api/v1/markets/99').status_code, 404)

    def test_legacy_uuid_no_database_fallback(self):
        r = self.client.get('/api/v1/markets/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.rpc.calls, [])

    def test_invalid_and_out_of_bound_ids_fail_before_rpc(self):
        for value in ['-1', '00', '100', '1.5', '0x1']:
            with self.subTest(value=value):
                r = self.client.get('/api/v1/markets/' + value,
                                    headers={'Authorization': 'Bearer ' + TOKEN})
                self.assertEqual(r.status_code, 404)
        self.assertEqual(self.rpc.calls, [])

    def test_explicit_status_filter(self):
        x = self.client.get('/api/v1/markets?status=resolved').json()
        self.assertEqual(x['total'], 1)
        self.assertEqual(x['markets'][0]['id'], '2')
        self.assertFalse(x['complete'])
        self.assertEqual(x['view']['totals_scope'], 'full_snapshot')

    def test_open_empty_is_success(self):
        r = self.client.get('/api/v1/markets?status=open')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['markets'], [])

    def test_pagination_is_explicit(self):
        x = self.client.get('/api/v1/markets?limit=1&offset=1').json()
        self.assertEqual(x['returned'], 1)
        self.assertEqual(x['total'], 3)
        self.assertFalse(x['complete'])
        self.assertEqual(x['markets'][0]['id'], '1')

    def test_category_filter(self):
        x = self.client.get('/api/v1/markets?category=RECOVERY').json()
        self.assertEqual(x['total'], 3)

    def test_unknown_and_legacy_queries_are_not_reactivated(self):
        for query in ['include_legacy=true', 'url=https://evil.invalid', 'rpc=https://evil.invalid', 'status=all&status=open']:
            with self.subTest(query=query):
                self.assertEqual(self.client.get('/api/v1/markets?' + query).status_code, 400)
        self.assertEqual(self.rpc.calls, [])

    def test_alias_rejects_queries(self):
        self.assertEqual(self.client.get('/api/v1/recovery/markets?status=open').status_code, 400)
        self.assertEqual(self.rpc.calls, [])

    def test_detail_rejects_queries(self):
        self.assertEqual(self.client.get('/api/v1/markets/2?url=x').status_code, 400)
        self.assertEqual(self.rpc.calls, [])

    def test_invalid_filters_fail_before_rpc(self):
        for query in ['limit=0', 'limit=101', 'offset=-1', 'status=unknown']:
            with self.subTest(query=query):
                self.assertEqual(self.client.get('/api/v1/markets?' + query).status_code, 422)
        self.assertEqual(self.rpc.calls, [])

    def test_no_cross_deployment_image_mapping(self):
        r = self.client.get('/api/v1/markets/images/all')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {})
        self.assertEqual(self.rpc.calls, [])

    def test_mutations_blocked_even_with_admin_token(self):
        for method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            for path in ['/api/v1/markets', '/api/v1/markets/2/resolve', '/api/v1/recovery/markets']:
                with self.subTest(method=method, path=path):
                    r = self.client.request(method, path, content='not even JSON',
                                            headers={'Authorization': 'Bearer ' + TOKEN})
                    self.assertEqual(r.status_code, 503)
                    self.assertEqual(r.json()['code'], 'RECOVERY_READ_ONLY')
        self.assertEqual(self.rpc.calls, [])

    def test_private_routes_still_require_auth(self):
        for path in ['/api/v1/users', '/api/v1/chain/events', '/api/v1/admin', '/.env']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.rpc.calls, [])

    def test_url_credentials_rejected(self):
        self.assertEqual(self.client.get('/api/v1/markets?access_token=secret').status_code, 400)
        self.assertEqual(self.rpc.calls, [])

    def test_configuration_mismatch_fails_closed(self):
        with patch.object(markets.settings, 'PREDICTION_MARKET_ADDRESS', '0x'+'0'*40):
            r = self.client.get('/api/v1/markets')
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()['detail']['code'], 'RECOVERY_CONFIG_MISMATCH')
        self.assertEqual(self.rpc.calls, [])

    def test_busy_fails_without_rpc(self):
        slots = threading.BoundedSemaphore(1)
        slots.acquire()
        with patch.object(markets, '_slots', slots):
            r = self.client.get('/api/v1/markets')
        self.assertEqual(r.status_code, 503)
        self.assertEqual(self.rpc.calls, [])

    def test_failed_rpc_does_not_return_legacy_data(self):
        self.rpc.chain = '0x1'
        r = self.client.get('/api/v1/markets')
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()['detail']['code'], 'WRONG_CHAIN')
        self.assertNotIn('markets', r.json())

    def test_arbitrary_exception_does_not_leak_secret(self):
        with patch.object(self.catalog, 'snapshot', side_effect=RuntimeError('sensitive-secret')):
            r = self.client.get('/api/v1/markets')
        self.assertEqual(r.status_code, 503)
        self.assertNotIn('sensitive-secret', r.text)

    def test_no_store(self):
        r = self.client.get('/api/v1/markets')
        self.assertEqual(r.headers['cache-control'], 'no-store')

    def test_cors_allowlisted_origin(self):
        r = self.client.get('/api/v1/markets', headers={'Origin': 'https://cryptopredict.app'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['access-control-allow-origin'], 'https://cryptopredict.app')
        self.assertNotIn('access-control-allow-credentials', r.headers)

    def test_invalid_preflight_origin(self):
        r = self.client.options('/api/v1/markets', headers={
            'Origin': 'https://evil.invalid', 'Access-Control-Request-Method': 'GET'})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.rpc.calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
