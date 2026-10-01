import asyncio
import copy
import json
from pathlib import Path
import sys
import time
import unittest

from app.services.chain_catalog import *

NOW=int(time.time())
BLOCK_HASH='0x'+'a'*64
DEPLOY_HASH='0x'+'b'*64
RUN='c'*32
BACKEND_RUN='d'*32


def word(n):return int(n).to_bytes(32,'big')
def wordhex(n):return '0x'+word(n).hex()
def addresshex(a):return '0x'+(b'\0'*12+bytes.fromhex(a[2:])).hex()


def market_tuple(mid=0, *, currency=1, status=3, yes=125000000, no=0, outcome=0, question='Recovery test', expires=None):
    strings=[question,'recovery','TEST']
    vals=[mid, int(MARKET,16), 0,0,0,0,1,expires or NOW-500,yes,no,0,status,outcome,0,currency]
    tail=b''
    for field, text in zip([2,3,4],strings):
        b=text.encode();vals[field]=15*32+len(tail);tail+=word(len(b))+b+b'\0'*((-len(b))%32)
    return '0x'+(word(32)+b''.join(word(n) for n in vals)+tail).hex()


class FakeRPC:
    def __init__(self):
        self.calls=[];self.count=3;self.chain='0x14a34';self.safe_stamp=NOW-60;self.bad={};self.reorg=False
        self.rows={0:market_tuple(0),1:market_tuple(1),2:market_tuple(2,status=2,outcome=2,yes=100000000,no=100000000)}
        self.escrows={0:0,1:0,2:0}
    def __call__(self,method,params,deadline):
        self.calls.append((method,copy.deepcopy(params)))
        if method in self.bad:return self.bad[method]
        if method=='eth_chainId':return self.chain
        if method=='eth_getBlockByNumber':
            if params[0]=='0x64':return {'number':'0x64','timestamp':hex(NOW-6000),'hash':DEPLOY_HASH}
            return {'number':'0xc8','timestamp':hex(self.safe_stamp),'hash':('0x'+'9'*64 if self.reorg and params[0]=='0xc8' else BLOCK_HASH)}
        if method=='eth_getTransactionReceipt':return {'status':'0x1','blockNumber':'0x64','blockHash':DEPLOY_HASH,'contractAddress':MARKET,'transactionHash':DEPLOY_TX}
        if method=='eth_getCode':return '0x123456'
        if method!='eth_call':raise AssertionError(method)
        opts,tag=params
        if tag!='0xc8':raise AssertionError(tag)
        name=next(k for k,v in SELECTORS.items() if opts['data'].startswith(v))
        if name in self.bad:return self.bad[name]
        if name=='decimals':return wordhex(DECIMALS[next(i for i,a in TOKENS.items() if a==opts['to'])])
        if name in ('cpredToken','usdcToken','usdtToken'):return addresshex(TOKENS[{'cpredToken':3,'usdcToken':1,'usdtToken':2}[name]])
        if name in ('positionMarket','presaleStaking'):return addresshex(ZERO)
        if name=='marketCount':return wordhex(self.count)
        mid=int(opts['data'][10:],16)
        if name=='getMarket':return self.rows[mid]
        if name=='marketEscrow':return wordhex(self.escrows[mid])
        if name=='marketToken':return addresshex(TOKENS[decode_market(self.rows[mid],mid)['currency_index']])
        raise AssertionError(name)


class CodecTests(unittest.TestCase):
    def test_tuple(self):
        r=decode_market(market_tuple(2,status=2,outcome=2,question='Verifica sì?'),2)
        self.assertEqual(r['question'],'Verifica sì?');self.assertEqual(r['id'],'2')
    def test_big_integer_precision(self):
        v=2**128+123456789;r=decode_market(market_tuple(yes=v),0);self.assertEqual(r['yes_pool_raw'],str(v))
    def test_format_six(self):self.assertEqual(format_units(100000001,6),'100.000001')
    def test_format_eighteen(self):self.assertEqual(format_units(1,18),'0.000000000000000001')
    def test_format_zero(self):self.assertEqual(format_units(0,6),'0')
    def test_wrong_id(self):
        with self.assertRaisesRegex(ReadError,'ID_MISMATCH'):decode_market(market_tuple(0),1)
    def test_zero_value_is_valid(self):self.assertEqual(uint_result(wordhex(0)),0)
    def test_truncated_word(self):
        with self.assertRaises(ReadError):uint_result('0x01')
    def test_bad_address_padding(self):
        with self.assertRaises(ReadError):address_result(wordhex(2**200))
    def test_bad_hex(self):
        for raw in ('0x0','0xxx','hello',None,'0xGG'):
            with self.subTest(raw=raw),self.assertRaises(ReadError):raw_bytes(raw)
    def test_bad_tuple_offset(self):
        x=bytearray(bytes.fromhex(market_tuple()[2:]));x[:32]=word(64)
        with self.assertRaises(ReadError):decode_market('0x'+x.hex(),0)
    def test_bad_string_offset(self):
        x=bytearray(bytes.fromhex(market_tuple()[2:]));x[96:128]=word(0)
        with self.assertRaises(ReadError):decode_market('0x'+x.hex(),0)
    def test_bad_boolean(self):
        x=bytearray(bytes.fromhex(market_tuple()[2:]));x[224:256]=word(2)
        with self.assertRaises(ReadError):decode_market('0x'+x.hex(),0)
    def test_bad_enum(self):
        with self.assertRaises(ReadError):decode_market(market_tuple(currency=9),0)
    def test_inconsistent_outcome(self):
        with self.assertRaises(ReadError):decode_market(market_tuple(status=0,outcome=1),0)
    def test_extra_data(self):
        with self.assertRaises(ReadError):decode_market(market_tuple()+'00'*32,0)
    def test_question_limit(self):
        with self.assertRaises(ReadError):decode_market(market_tuple(question='X'*4097),0)
    def test_invalid_utf8(self):
        x=bytearray(bytes.fromhex(market_tuple()[2:]));x[544]=255
        with self.assertRaises(ReadError):decode_market('0x'+x.hex(),0)
    def test_nonzero_padding(self):
        x=bytearray(bytes.fromhex(market_tuple()[2:]));x[-1]=1
        with self.assertRaises(ReadError):decode_market('0x'+x.hex(),0)
    def test_quantity(self):
        for v in (1,True,'0x00','0x','0x-1'):
            with self.subTest(v=v),self.assertRaises(ReadError):quantity(v)
    def test_market_id_bound(self):
        for v in (-1,100,True,None):
            with self.subTest(v=v),self.assertRaises(ReadError):call_data('getMarket',v)
    def test_no_extra_args(self):
        with self.assertRaises(ReadError):call_data('marketCount',1)
    def test_rpc_denies_transaction_method(self):
        with self.assertRaisesRegex(ReadError,'RPC_METHOD_BLOCKED'):FixedRPC()('eth_sendRawTransaction',[],time.monotonic()+1)


class CatalogTests(unittest.TestCase):
    def make(self):
        r=FakeRPC();return r,Catalog(r,clock=lambda:NOW)
    def test_success(self):
        r,c=self.make();x=c.snapshot();self.assertEqual(x['market_count'],3);self.assertEqual(x['markets'][0]['outcome'],'NO');self.assertEqual(x['totals_by_currency'][0]['deposited_raw'],'450000000')
    def test_cache(self):
        r,c=self.make();first=c.snapshot();n=len(r.calls);second=c.snapshot();self.assertEqual(len(r.calls),n);self.assertTrue(second['cache']['hit']);self.assertEqual(first['snapshot_digest'],second['snapshot_digest'])
    def test_no_cache_mutation(self):
        r,c=self.make();x=c.snapshot();x['markets'][0]['question']='evil';self.assertNotEqual(c.snapshot()['markets'][0]['question'],'evil')
    def test_same_block(self):
        r,c=self.make();c.snapshot();self.assertTrue(all(p[-1]=='0xc8' for m,p in r.calls if m=='eth_call'))
    def test_wrong_chain(self):
        r,c=self.make();r.chain='0x1'
        with self.assertRaisesRegex(ReadError,'WRONG_CHAIN'):c.snapshot()
    def test_token_identity(self):
        r,c=self.make();r.bad['usdcToken']=addresshex(ZERO)
        with self.assertRaisesRegex(ReadError,'COLLATERAL_IDENTITY'):c.snapshot()
    def test_decimals(self):
        r,c=self.make();r.bad['decimals']=wordhex(9)
        with self.assertRaisesRegex(ReadError,'TOKEN_DECIMALS'):c.snapshot()
    def test_extension(self):
        r,c=self.make();r.bad['positionMarket']=addresshex(MARKET)
        with self.assertRaisesRegex(ReadError,'LEGACY_EXTENSION'):c.snapshot()
    def test_no_bytecode(self):
        r,c=self.make();r.bad['eth_getCode']='0x'
        with self.assertRaisesRegex(ReadError,'BYTECODE_MISSING'):c.snapshot()
    def test_deploy_wrong_contract(self):
        r,c=self.make();d=r('eth_getTransactionReceipt',[],0);d['contractAddress']=ZERO;r.bad['eth_getTransactionReceipt']=d
        with self.assertRaisesRegex(ReadError,'DEPLOYMENT_MISMATCH'):c.snapshot()
    def test_deploy_failed(self):
        r,c=self.make();d=r('eth_getTransactionReceipt',[],0);d['status']='0x0';r.bad['eth_getTransactionReceipt']=d
        with self.assertRaisesRegex(ReadError,'DEPLOYMENT_MISMATCH'):c.snapshot()
    def test_reorg(self):
        r,c=self.make();r.reorg=True
        with self.assertRaisesRegex(ReadError,'SNAPSHOT_REORG'):c.snapshot()
    def test_too_many_markets(self):
        r,c=self.make();r.count=101
        with self.assertRaisesRegex(ReadError,'CATALOG_LIMIT_EXCEEDED'):c.snapshot()
    def test_empty_catalog_not_failure(self):
        r,c=self.make();r.count=0;self.assertEqual(c.snapshot()['market_count'],0)
    def test_expired_open(self):
        r,c=self.make();r.rows[0]=market_tuple(status=0);self.assertEqual(c.snapshot()['markets'][-1]['state'],'awaiting_resolution')
    def test_open_before_expiry(self):
        r,c=self.make();r.rows[0]=market_tuple(status=0,expires=NOW+3600);self.assertEqual(c.snapshot()['markets'][-1]['state'],'open')
    def test_separate_currencies(self):
        r,c=self.make();r.rows[1]=market_tuple(1,currency=0,yes=10**18);x=c.snapshot();self.assertEqual(len(x['totals_by_currency']),2);self.assertEqual(x['totals_by_currency'][0]['currency'],'ETH')
    def test_percent_is_not_probability(self):
        r,c=self.make();row=c.snapshot()['markets'][-1];self.assertEqual(row['deposit_split_bps'],{'yes':10000,'no':0});self.assertFalse(row['split_is_probability'])
    def test_safe_stale(self):
        r,c=self.make();r.safe_stamp=NOW-4000
        with self.assertRaisesRegex(ReadError,'CLOCK_OR_LAG'):c.snapshot()
    def test_safe_future(self):
        r,c=self.make();r.safe_stamp=NOW+121
        with self.assertRaisesRegex(ReadError,'CLOCK_OR_LAG'):c.snapshot()
    def test_escrow_above_deposits(self):
        r,c=self.make();r.escrows[0]=126000000
        with self.assertRaisesRegex(ReadError,'ESCROW_EXCEEDS'):c.snapshot()
    def test_cached_failure_not_stale_success(self):
        r,c=self.make();c.snapshot();c.cached_at-=31;r.chain='0x1'
        with self.assertRaises(ReadError):c.snapshot()
        n=len(r.calls)
        with self.assertRaises(ReadError):c.snapshot()
        self.assertEqual(len(r.calls),n);self.assertIsNone(c.cached)
    def test_never_write_rpc_or_db(self):
        r,c=self.make();x=c.snapshot();self.assertTrue(all(m in {'eth_chainId','eth_call','eth_getBlockByNumber','eth_getCode','eth_getTransactionReceipt'} for m,p in r.calls));self.assertFalse(x['database_used'])


if __name__=='__main__':unittest.main(verbosity=2)
