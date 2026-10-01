"""Fixed-contract Base Sepolia read service. No signing, DB client, or secrets.

Snapshot calls use ONE explicit safe block number, followed by a hash check.
Amounts are decimal strings of atomic units. Deposit split is NOT a price or
probability. Errors never return RPC response bodies or request credentials.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

CHAIN_ID = 84532
MARKET = '0x76f9660a8801f97a8f5d1ac2036b9a9c22495436'
DEPLOY_TX = '0xd5a65564232a9f3681c45c27e7829c34e8955ed7c9f67d46a7428e75dc351f74'
ZERO = '0x' + '0' * 40
RPC_URL = 'https://sepolia.base.org'
SCHEMA = 'cryptopredict-recovery-catalog-v1'
MAX_MARKETS = 100
TOKENS = {0: ZERO, 1: '0x8a54f0e841cfca5fa654912af33ccd121d182311',
          2: '0xabb48e1693df04fb894843e52b239d5c5d0ab871',
          3: '0xec937bf3123874115edcbbe1b3802c95f572e8e5'}
DECIMALS = {0: 18, 1: 6, 2: 6, 3: 18}
SYMBOLS = {0: 'ETH', 1: 'MockUSDC', 2: 'MockUSDT', 3: 'CPRED'}
SELECTORS = {'marketCount': '0xec979082', 'getMarket': '0xeb44fdd3',
             'marketEscrow': '0xd632363c', 'marketToken': '0xcda9a605',
             'cpredToken': '0x01ce05e7', 'usdcToken': '0x11eac855',
             'usdtToken': '0xa98ad46c', 'positionMarket': '0x62fc5c7d',
             'presaleStaking': '0xd742d71c', 'decimals': '0x313ce567'}
HEX = re.compile(r'0x(?:[0-9a-fA-F]{2})*')
HASH = re.compile(r'0x[0-9a-fA-F]{64}')
QUANTITY = re.compile(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)')


class ReadError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def quantity(value: Any) -> int:
    if not isinstance(value, str) or len(value) > 66 or not QUANTITY.fullmatch(value):
        raise ReadError('RPC_INVALID_QUANTITY')
    return int(value, 16)


def raw_bytes(value: Any, max_bytes: int = 16384) -> bytes:
    if not isinstance(value, str) or len(value) > 2 + max_bytes * 2 or not HEX.fullmatch(value):
        raise ReadError('ABI_INVALID_HEX')
    return bytes.fromhex(value[2:])


def uint_result(value: Any) -> int:
    data = raw_bytes(value, 32)
    if len(data) != 32:
        raise ReadError('ABI_INVALID_WORD')
    return int.from_bytes(data, 'big')


def address_result(value: Any) -> str:
    data = raw_bytes(value, 32)
    if len(data) != 32 or data[:12] != b'\0' * 12:
        raise ReadError('ABI_INVALID_ADDRESS')
    return '0x' + data[12:].hex()


def call_data(name: str, market_id: int | None = None) -> str:
    value = SELECTORS[name]
    if name in {'getMarket', 'marketEscrow', 'marketToken'}:
        if type(market_id) is not int or not 0 <= market_id < MAX_MARKETS:
            raise ReadError('MARKET_ID_INVALID')
        return value + format(market_id, '064x')
    if market_id is not None:
        raise ReadError('CALL_ARGUMENT_INVALID')
    return value


def decode_market(value: Any, expected_id: int) -> dict:
    """Strict decoder for the single canonical 15-field getMarket tuple.

    ABI layout is verified against the repository contract and cross-checked
    with eth_abi on the user's already installed web3 environment before startup.
    """
    data = raw_bytes(value)
    if len(data) < 32 + 15 * 32 or len(data) % 32:
        raise ReadError('ABI_INVALID_TUPLE')
    if int.from_bytes(data[:32], 'big') != 32:
        raise ReadError('ABI_INVALID_TUPLE_OFFSET')
    payload = data[32:]
    words = [payload[i*32:(i+1)*32] for i in range(15)]
    vals = [int.from_bytes(w, 'big') for w in words]
    if vals[0] != expected_id:
        raise ReadError('MARKET_ID_MISMATCH')
    if vals[6] not in (0, 1) or vals[11] not in (0, 1, 2, 3) or vals[12] not in (0, 1, 2) or vals[14] not in (0, 1, 2, 3):
        raise ReadError('ABI_INVALID_ENUM_OR_BOOL')
    if words[1][:12] != b'\0' * 12 or words[13][:12] != b'\0' * 12:
        raise ReadError('ABI_INVALID_ADDRESS')
    strings = []
    cursor = 15 * 32
    for field, bound in ((2, 4096), (3, 128), (4, 64)):
        offset = vals[field]
        if offset != cursor or offset + 32 > len(payload):
            raise ReadError('ABI_INVALID_STRING_OFFSET')
        length = int.from_bytes(payload[offset:offset+32], 'big')
        padded = ((length + 31) // 32) * 32
        end = offset + 32 + padded
        if length > bound or end > len(payload):
            raise ReadError('ABI_STRING_LIMIT')
        if any(payload[offset+32+length:end]):
            raise ReadError('ABI_NONZERO_PADDING')
        try:
            text = payload[offset+32:offset+32+length].decode('utf-8', errors='strict')
        except UnicodeError:
            raise ReadError('ABI_INVALID_UTF8') from None
        if any(ord(c) < 32 and c not in '\n\t' for c in text):
            raise ReadError('ABI_CONTROL_TEXT')
        strings.append(text)
        cursor = end
    if cursor != len(payload):
        raise ReadError('ABI_TRAILING_BYTES')
    if not strings[0] or vals[7] > 253402300799:
        raise ReadError('MARKET_METADATA_INVALID')
    if vals[10] != 0:
        raise ReadError('RECOVERY_YIELD_NOT_ZERO')
    if (vals[11] == 2) != (vals[12] in (1, 2)):
        raise ReadError('MARKET_STATUS_OUTCOME_MISMATCH')
    return {'id': str(vals[0]), 'creator': '0x' + words[1][12:].hex(),
            'question': strings[0], 'category': strings[1], 'asset_symbol': strings[2],
            'target_price_raw': str(vals[5]), 'target_above': bool(vals[6]),
            'expires_at': vals[7], 'yes_pool_raw': str(vals[8]), 'no_pool_raw': str(vals[9]),
            'status_code': vals[11], 'outcome_code': vals[12], 'currency_index': vals[14]}


def format_units(value: int, decimals: int) -> str:
    if type(value) is not int or value < 0 or not 0 <= decimals <= 18:
        raise ValueError('Invalid amount')
    whole, fraction = divmod(value, 10 ** decimals)
    suffix = str(fraction).zfill(decimals).rstrip('0') if decimals else ''
    return str(whole) + ('.' + suffix if suffix else '')


class FixedRPC:
    """Only this class knows the RPC URL; neither HTTP clients nor env can override it."""
    def __init__(self):
        self.calls = 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def __call__(self, method: str, params: list, deadline: float) -> Any:
        allowed = {'eth_chainId', 'eth_getBlockByNumber', 'eth_getTransactionReceipt', 'eth_getCode', 'eth_call'}
        if method not in allowed:
            raise ReadError('RPC_METHOD_BLOCKED')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ReadError('RPC_SNAPSHOT_TIMEOUT')
        self.calls += 1
        ident = self.calls
        body = json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params}).encode()
        req = urllib.request.Request(RPC_URL, data=body, method='POST',
              headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                       'User-Agent': 'CryptoPredict-ReadBridge/1.0'})
        try:
            with self.opener.open(req, timeout=min(8, remaining)) as r:
                if r.status != 200:
                    raise ReadError('RPC_HTTP_ERROR')
                raw = r.read(262145)
            if len(raw) > 262144:
                raise ReadError('RPC_RESPONSE_LIMIT')
            obj = json.loads(raw)
        except ReadError:
            raise
        except Exception:
            raise ReadError('RPC_UNAVAILABLE') from None
        if not isinstance(obj, dict) or obj.get('jsonrpc') != '2.0' or obj.get('id') != ident or 'error' in obj or 'result' not in obj:
            raise ReadError('RPC_RESPONSE_REJECTED')
        return obj['result']


class Catalog:
    def __init__(self, rpc=None, *, clock=time.time, monotonic=time.monotonic):
        self.rpc = rpc or FixedRPC()
        self.clock = clock
        self.mono = monotonic
        self.lock = threading.Lock()
        self.cached = None
        self.cached_at = 0.0
        self.failure_at = -999999.0
        self.failure = None

    def snapshot(self) -> dict:
        with self.lock:
            tick = self.mono()
            if self.failure and tick - self.failure_at < 10:
                raise ReadError(self.failure)
            if self.cached is not None and tick - self.cached_at < 30:
                return self.envelope(self.cached, True)
            try:
                value = self.fetch()
            except Exception as exc:
                self.cached = None  # Never silently return a last-known snapshot after failure.
                self.failure = exc.code if isinstance(exc, ReadError) else 'SNAPSHOT_FAILED'
                self.failure_at = self.mono()
                raise ReadError(self.failure) from None
            self.failure = None
            self.cached, self.cached_at = value, self.mono()
            return self.envelope(value, False)

    def envelope(self, value, cached):
        result = copy.deepcopy(value)
        result['served_at'] = datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()
        result['cache'] = {'hit': cached, 'max_age_seconds': 30,
                           'age_seconds': max(0, round(self.mono() - self.cached_at, 3))}
        return result

    def fetch(self) -> dict:
        deadline = time.monotonic() + 65
        def rpc(method, params):
            return self.rpc(method, params, deadline)
        if quantity(rpc('eth_chainId', [])) != CHAIN_ID:
            raise ReadError('WRONG_CHAIN')
        block = rpc('eth_getBlockByNumber', ['safe', False])
        if not isinstance(block, dict) or not HASH.fullmatch(str(block.get('hash', ''))):
            raise ReadError('SAFE_BLOCK_UNAVAILABLE')
        number, stamp = quantity(block.get('number')), quantity(block.get('timestamp'))
        block_hash = block['hash'].lower()
        if stamp > self.clock() + 120 or self.clock() - stamp > 3600:
            raise ReadError('SAFE_BLOCK_CLOCK_OR_LAG')
        tag = hex(number)
        receipt = rpc('eth_getTransactionReceipt', [DEPLOY_TX])
        if (not isinstance(receipt, dict) or receipt.get('status') != '0x1'
                or str(receipt.get('contractAddress', '')).lower() != MARKET
                or str(receipt.get('transactionHash', '')).lower() != DEPLOY_TX
                or not HASH.fullmatch(str(receipt.get('blockHash', '')))
                or quantity(receipt.get('blockNumber')) > number):
            raise ReadError('DEPLOYMENT_MISMATCH')
        deploy_block = rpc('eth_getBlockByNumber', [receipt['blockNumber'], False])
        if not isinstance(deploy_block, dict) or str(deploy_block.get('hash', '')).lower() != str(receipt.get('blockHash', '')).lower():
            raise ReadError('DEPLOYMENT_REORG')
        if not raw_bytes(rpc('eth_getCode', [MARKET, tag]), 49152):
            raise ReadError('CONTRACT_BYTECODE_MISSING')
        def call(name, mid=None, target=MARKET):
            return rpc('eth_call', [{'to': target, 'data': call_data(name, mid)}, tag])
        for getter, idx in (('cpredToken', 3), ('usdcToken', 1), ('usdtToken', 2)):
            if address_result(call(getter)) != TOKENS[idx]:
                raise ReadError('COLLATERAL_IDENTITY_MISMATCH')
            if not raw_bytes(rpc('eth_getCode', [TOKENS[idx], tag]), 49152):
                raise ReadError('TOKEN_BYTECODE_MISSING')
            if uint_result(call('decimals', target=TOKENS[idx])) != DECIMALS[idx]:
                raise ReadError('TOKEN_DECIMALS_MISMATCH')
        if any(address_result(call(k)) != ZERO for k in ('positionMarket', 'presaleStaking')):
            raise ReadError('LEGACY_EXTENSION_CONNECTED')
        count = uint_result(call('marketCount'))
        if count > MAX_MARKETS:
            raise ReadError('CATALOG_LIMIT_EXCEEDED')
        rows, totals = [], {}
        for mid in range(count):
            row = decode_market(call('getMarket', mid), mid)
            currency = row['currency_index']
            if address_result(call('marketToken', mid)) != TOKENS[currency]:
                raise ReadError('MARKET_TOKEN_MISMATCH')
            escrow = uint_result(call('marketEscrow', mid))
            yes, no = int(row['yes_pool_raw']), int(row['no_pool_raw'])
            deposited = yes + no
            if escrow > deposited:
                raise ReadError('ESCROW_EXCEEDS_DEPOSITS')
            status = row['status_code']
            effective = ('awaiting_resolution' if row['expires_at'] <= stamp else 'open') if status == 0 else ('closed', 'resolved', 'cancelled')[status - 1]
            row.update(currency=SYMBOLS[currency], decimals=DECIMALS[currency],
                       token_address=TOKENS[currency], escrow_raw=str(escrow),
                       deposited_raw=str(deposited), state=effective,
                       outcome=('unresolved', 'YES', 'NO')[row['outcome_code']],
                       deposit_split_bps={'yes': yes * 10000 // deposited if deposited else None,
                                          'no': (10000 - yes * 10000 // deposited) if deposited else None},
                       split_is_probability=False, transaction_actions_enabled=False)
            rows.append(row)
            total = totals.setdefault(currency, {'deposited': 0, 'escrow': 0})
            total['deposited'] += deposited; total['escrow'] += escrow
        final = rpc('eth_getBlockByNumber', [tag, False])
        if not isinstance(final, dict) or str(final.get('hash', '')).lower() != block_hash:
            raise ReadError('SNAPSHOT_REORG')
        catalog = {'schema': SCHEMA, 'chain_id': CHAIN_ID, 'contract_address': MARKET,
                   'snapshot': {'block_number': number, 'block_hash': block_hash,
                       'block_timestamp': stamp, 'requested_tag': 'safe',
                       'all_reads_at_same_block': True, 'hash_rechecked': True,
                       'observed_at': datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()},
                   'source': 'base-sepolia-rpc', 'database_used': False,
                   'legacy_data_included': False, 'automatic_jobs': False,
                   'transaction_actions_enabled': False, 'full_application_readiness': False,
                   'market_count': count, 'complete': True, 'limit': MAX_MARKETS,
                   'markets': list(reversed(rows)),
                   'totals_by_currency': [{'currency_index': c, 'currency': SYMBOLS[c],
                      'decimals': DECIMALS[c], 'deposited_raw': str(t['deposited']),
                      'escrow_raw': str(t['escrow'])} for c, t in sorted(totals.items())],
                   'trust': 'Trusted RPC read; not an independent cryptographic audit or oracle.'}
        catalog['snapshot_digest'] = hashlib.sha256(json.dumps(catalog, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        return catalog
