#!/usr/bin/env python3
"""Independent browser and model regressions for G/H/I stock-game features.

Usage: python ghi_regression.py --url http://127.0.0.1:8765/
Requires Python Playwright and Chromium. Uses independent local-only browser state.
"""
import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
import sys
import unittest
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--url',default='http://127.0.0.1:8765/')
parser.add_argument('--artifacts',help='Directory for screenshots (default: a new temporary directory)')
parser.add_argument('--chromium',default=os.environ.get('CHROMIUM_PATH'),help='Chromium executable; otherwise use a detected or Playwright-installed browser')
args,remaining=parser.parse_known_args()
BASE=args.url.rstrip('/')+'/'
ARTIFACTS=Path(args.artifacts or tempfile.mkdtemp(prefix='kabu-mobile-ux-'))
BROWSER_PATH=args.chromium or shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')

class GHIFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw=sync_playwright().start()
        cls.browser=cls.pw.chromium.launch(executable_path=BROWSER_PATH,headless=True,args=['--no-sandbox'])
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop()
    def setUp(self):
        self.ctx=self.browser.new_context(viewport={'width':412,'height':850},device_scale_factor=2.625,is_mobile=True,has_touch=True,ignore_https_errors=True)
        # Keep the opening market and corporate-news fixture reproducible across runs.
        self.ctx.add_init_script('Math.random = () => 0.123456789;')
        self.page=self.ctx.new_page();self.page.set_default_timeout(5000)
        self.errors=[];self.page.on('pageerror',lambda error:self.errors.append(str(error)))
        self.page.goto(BASE)
        self.ready()
    def ready(self):
        self.page.wait_for_function('window.__myAccount && !document.querySelector("#boot-splash")',timeout=15000)
    def tearDown(self):
        try:self.page.screenshot(path=str(ARTIFACTS/(self._testMethodName+'.png')))
        finally:self.ctx.close()
        self.assertEqual([],self.errors,'JavaScript errors: '+json.dumps(self.errors,ensure_ascii=False))
    def route(self,name):
        nav=self.page.locator('.mob-nav a[href="#'+name+'"]')
        if nav.count():nav.tap()
        else:
            self.page.locator('#mob-more').tap()
            self.page.locator('#mob-sheet a[href="#'+name+'"]').tap()
        self.page.wait_for_function('(name)=>document.body.dataset.page===name',arg=name)
    def view(self,name):
        self.page.locator('#stock-info-nav [data-stock-view="'+name+'"]').tap()
        self.page.wait_for_timeout(100)
    def account(self):
        return self.page.evaluate('JSON.stringify(window.__myAccount)')
    def selected_code(self):
        return self.page.locator('#stock-info-code').inner_text().strip()
    def choose_stock(self,code):
        self.route('company')
        self.page.locator('.company-toolbar .mob-col-toggle').tap()
        options=self.page.locator('#company-select option').evaluate_all('es=>es.map(e=>({value:e.value,text:e.textContent}))')
        opt=next(o for o in options if code in o['text'])
        self.page.locator('#company-select').select_option(opt['value'])
        self.view('chart')
        self.assertIn(code,self.selected_code())
    def place_limit(self,product='cash',qty=100):
        self.route('order')
        self.page.locator('input[name="product"][value="'+product+'"]').check()
        self.page.locator('input[name="otype"][value="limit"]').check()
        # Read the price band through its visible disclosure in simple mode.
        extras=self.page.locator('#order-extra-info')
        if extras.count() and not extras.evaluate('(e)=>e.open'):
            extras.locator('summary').tap()
        bounds=self.page.locator('#of-limit').inner_text().replace(',','')
        import re
        lower=float(re.findall(r'\d+(?:\.\d+)?',bounds)[0])
        self.page.locator('#o-limit').fill(str(lower))
        self.page.locator('#o-qty').fill(str(qty))
        self.page.locator('#o-submit').tap();self.page.locator('#o-yes').tap()
        key='orders' if product=='cash' else 'creditOrders'
        order=self.page.evaluate('(key)=>JSON.parse(JSON.stringify(window.__myAccount[key].at(-1)))',key)
        self.assertIsNotNone(order)
        return order
    def buy_market(self,product='cash'):
        self.route('order')
        self.page.locator('input[name="product"][value="'+product+'"]').check()
        self.page.locator('input[name="otype"][value="market"]').check()
        self.page.locator('#o-qty').fill('100')
        self.page.locator('#o-submit').tap();self.page.locator('#o-yes').tap()
    def save_reload(self):
        self.route('settings');self.page.locator('#st-tab-save').tap()
        self.page.locator('#persist-save-now').tap();self.page.wait_for_timeout(600)
        self.page.reload();self.ready()
    def model_check(self,body):
        result=self.page.evaluate('''() => {
          const fail=[];const check=(ok,msg)=>{if(!ok)fail.push(msg)};
          const make=()=>{const m=new Market(4312,1),a=new Account(3000000),k=m.stocks[0];return {m,a,k}};
          const snap=a=>JSON.stringify(a);
          const ordinary=(a,m,k,product,qty=300)=>product==='cash'
            ? a.place({code:k.code,side:'buy',type:'limit',limit:k.lower,qty},m)
            : a.placeCredit({code:k.code,side:'buy',type:'limit',limit:k.lower,qty,operation:'open',creditType:'system'},m);
          '''+body+''';return fail;
        }''')
        self.assertEqual([],result,'; '.join(result))

    def test_g_simple_detail_and_active_advanced_visibility(self):
        self.route('order')
        self.assertEqual('simple',self.page.locator('#page-order').get_attribute('data-order-view'))
        self.assertFalse(self.page.locator('#order-extra-info').evaluate('(e)=>e.open'))
        for kind in ['market','limit']:
            self.assertTrue(self.page.locator('input[name="otype"][value="'+kind+'"]').is_visible())
        for kind in ['stop','ifd','oco']:
            self.assertFalse(self.page.locator('input[name="otype"][value="'+kind+'"]').is_visible())
        self.page.locator('#order-view-detail').tap()
        self.assertTrue(self.page.locator('#order-extra-info').evaluate('(e)=>e.open'))
        for kind in ['stop','ifd','oco']:
            self.assertTrue(self.page.locator('input[name="otype"][value="'+kind+'"]').is_visible())
        self.page.locator('input[name="otype"][value="stop"]').check()
        self.assertTrue(self.page.locator('#order-view-simple').is_disabled())
        self.assertTrue(self.page.locator('input[name="otype"][value="stop"]').is_checked())
        self.assertTrue(self.page.locator('input[name="otype"][value="stop"]').is_visible())
        self.assertEqual('detail',self.page.locator('#page-order').get_attribute('data-order-view'))
        self.page.locator('input[name="otype"][value="market"]').check()
        self.page.locator('#order-view-simple').tap()
        self.assertEqual('simple',self.page.locator('#page-order').get_attribute('data-order-view'))
        self.assertEqual('true',self.page.locator('#order-view-simple').get_attribute('aria-pressed'))

    def test_g_mode_persistence_and_advanced_restoration(self):
        self.route('order');self.page.locator('#order-view-detail').tap()
        self.route('chart');self.route('order')
        self.assertEqual('detail',self.page.locator('#page-order').get_attribute('data-order-view'))
        self.page.locator('input[name="otype"][value="stop"]').check()
        self.save_reload();self.route('order')
        self.assertTrue(self.page.locator('input[name="otype"][value="stop"]').is_checked())
        self.assertTrue(self.page.locator('input[name="otype"][value="stop"]').is_visible())
        self.assertEqual('detail',self.page.locator('#page-order').get_attribute('data-order-view'))
        # Older saved advanced forms must remain visible even with a simple-mode preference.
        self.page.evaluate('localStorage.setItem("kabu-order-view","simple")')
        self.page.reload();self.ready();self.route('order')
        self.assertTrue(self.page.locator('input[name="otype"][value="stop"]').is_checked())
        self.assertTrue(self.page.locator('input[name="otype"][value="stop"]').is_visible())
        self.assertEqual('detail',self.page.locator('#page-order').get_attribute('data-order-view'))
        self.page.locator('input[name="otype"][value="market"]').check();self.page.locator('#order-view-simple').tap()
        self.save_reload();self.route('order')
        self.assertEqual('simple',self.page.locator('#page-order').get_attribute('data-order-view'))
        self.assertEqual('simple',self.page.evaluate('localStorage.getItem("kabu-order-view")'))

    def test_h_cash_and_credit_ui_amendment_requires_confirmation(self):
        for product in ['cash','credit']:
            with self.subTest(product=product):
                order=self.place_limit(product)
                self.route('chart');self.page.locator('#stock-orders-open').tap()
                row=self.page.locator(f'#stock-orders-list > li[data-order-product="{product}"][data-order-id="{order["id"]}"]')
                self.assertEqual(1,row.count())
                row.locator('[data-order-action="amend"]').tap()
                before=self.account()
                self.page.locator('#stock-order-price').fill('0');self.page.locator('#stock-order-review').tap()
                self.assertEqual(before,self.account(),'Invalid review mutated the account')
                self.assertTrue(self.page.locator('#stock-order-error').inner_text().strip())
                self.assertFalse(self.page.locator('#stock-order-confirm-wrap').is_visible())
                price=order['limit']+1
                self.page.locator('#stock-order-price').fill(str(price))
                self.assertEqual(before,self.account(),'Typing changed the pending order')
                self.page.locator('#stock-order-review').tap()
                self.assertEqual(before,self.account(),'Review changed the pending order before confirmation')
                self.page.locator('#stock-order-confirm').tap()
                updated=self.page.evaluate('([product,id])=>JSON.parse(JSON.stringify(window.__myAccount.pendingOrder(product,id)))',[product,order['id']])
                self.assertEqual(price,updated['limit']);self.assertEqual(order['qty'],updated['qty'])
                self.page.locator('#stock-orders-close').tap()
        self.assertEqual(2,len(self.page.evaluate('window.__myAccount.orderAmendments')))
        amended=self.account();self.save_reload();self.assertEqual(amended,self.account(),'Amended orders/audit history not restored')

    def test_h_manager_stock_filter_and_cancel_confirmation(self):
        order=self.place_limit('cash')
        self.route('chart');self.page.locator('#s-next').tap()
        self.page.locator('#stock-orders-open').tap()
        self.assertEqual(0,self.page.locator('#stock-orders-list > li').count())
        self.assertTrue(self.page.locator('#stock-orders-empty').is_visible())
        self.page.locator('#stock-orders-close').tap()
        self.page.evaluate('(code)=>window.dispatchEvent(new CustomEvent("kabu:open-stock-orders",{detail:{code}}))',order['code'])
        row=self.page.locator(f'#stock-orders-list > li[data-order-product="cash"][data-order-id="{order["id"]}"]')
        self.assertEqual(1,row.count())
        before=self.account();row.locator('[data-order-action="cancel"]').tap()
        self.assertEqual(before,self.account(),'Cancel acted before confirmation')
        self.page.locator('#stock-order-confirm').tap()
        self.assertFalse(self.page.evaluate('(id)=>window.__myAccount.orders.some(o=>o.id===id)',order['id']))
        self.assertTrue(self.page.evaluate('(id)=>window.__myAccount.closed.some(o=>o.id===id&&o.status==="canceled")',order['id']))

    def test_h_models_cash_credit_remaining_and_reserves(self):
        self.model_check('''
          for(const product of ['cash','credit']){
            const {m,a,k}=make(),r=ordinary(a,m,k,product);check(r.ok,product+' setup');if(!r.ok)continue;
            const o=r.order,price=stepPrice(o.limit,1,k.table),beforeId=o.id,nextId=product==='cash'?a.nextId:a.nextCreditOrderId;
            if(product==='cash')a.execute(o,o.limit,m,100);else a.executeCredit(o,o.limit,m,false,100);
            const fills=JSON.stringify(product==='cash'?a.execs:a.creditExecs),filled=o.filled,filledAmt=o.filledAmt;
            const key=a.limitAmendmentKey(product,o.id),valid=a.validateLimitAmendment(product,o.id,price,m,key);
            check(valid.ok,product+' partial amendment validates');
            const beforeReview=snap(a);a.validateLimitAmendment(product,o.id,price,m,key);check(snap(a)===beforeReview,product+' validation pure');
            const changed=a.amendLimitOrder(product,o.id,price,m,key);
            check(changed.ok,product+' partial amend succeeds');
            const updated=a.pendingOrder(product,o.id);
            check(updated.id===beforeId&&updated.qty===200,product+' keeps id and remaining qty');
            check(updated.origQty===300&&updated.filled===filled&&updated.filledAmt===filledAmt,product+' preserves original and filled data');
            check(JSON.stringify(product==='cash'?a.execs:a.creditExecs)===fills,product+' execution history unchanged');
            check((product==='cash'?a.nextId:a.nextCreditOrderId)===nextId,product+' no replacement order id');
            const reserve=product==='cash'?updated.reserve:updated.reserveMargin,expected=price*updated.qty/(product==='cash'?1:CREDIT_MAX_LEVERAGE);
            check(Math.abs(reserve-expected)<1e-6,product+' reserve uses remaining qty/new price');
          }
        ''')

    def test_h_invalid_and_insufficient_funds_do_not_mutate(self):
        self.model_check('''
          for(const product of ['cash','credit']){
            const {m,k}=make(),a=new Account(k.lower*100/(product==='cash'?1:CREDIT_MAX_LEVERAGE));
            const r=ordinary(a,m,k,product,100);check(r.ok,product+' tight setup');if(!r.ok)continue;
            const o=r.order,key=a.limitAmendmentKey(product,o.id);
            for(const price of [0,NaN,k.lower-1,k.upper+1,k.lower+0.123,k.upper]){
              const before=snap(a),v=a.amendLimitOrder(product,o.id,price,m,key);
              check(!v.ok,product+' invalid/funds rejects '+price);check(snap(a)===before,product+' rejects without mutation '+price);
            }
          }
        ''')

    def test_h_stale_keys_and_nonordinary_orders_rejected(self):
        self.model_check('''
          for(const product of ['cash','credit']){
            const {m,a,k}=make(),r=ordinary(a,m,k,product),o=r.order,price=stepPrice(o.limit,1,k.table);
            const old=a.limitAmendmentKey(product,o.id);
            if(product==='cash')a.execute(o,o.limit,m,100);else a.executeCredit(o,o.limit,m,false,100);
            let before=snap(a),v=a.amendLimitOrder(product,o.id,price,m,old);
            check(!v.ok&&snap(a)===before,product+' stale fill rejects unchanged');
            const current=a.limitAmendmentKey(product,o.id);v=a.amendLimitOrder(product,o.id,price,m,current);check(v.ok,product+' refreshed key succeeds');
            before=snap(a);v=a.amendLimitOrder(product,o.id,stepPrice(price,1,k.table),m,current);check(!v.ok&&snap(a)===before,product+' stale amended key rejects');
            const cancelKey=a.limitAmendmentKey(product,o.id);if(product==='cash')a.cancel(o.id,m);else a.cancelCredit(o.id,m);
            before=snap(a);v=a.amendLimitOrder(product,o.id,price,m,cancelKey);check(!v.ok&&snap(a)===before,product+' canceled rejects');
          }
          for(const product of ['cash','credit']){
            const {m,a,k}=make();
            const spec={product,code:k.code,side:'buy',type:'ifd',entryType:'limit',entryPrice:k.lower,exitPrice:k.upper,qty:100,operation:'open',creditType:'system'};
            const r=a.placeAdvanced(spec,m);check(r.ok,product+' IFD setup');if(!r.ok)continue;
            const before=snap(a),v=a.amendLimitOrder(product,r.order.id,stepPrice(k.lower,1,k.table),m,a.limitAmendmentKey(product,r.order.id));
            check(!v.ok&&snap(a)===before,product+' IFD entry not ordinary editable');
          }
        ''')

    def test_h_market_stop_oco_and_closing_amendment_rejected(self):
        self.model_check('''
          for(const product of ['cash','credit']){
            for(const kind of ['market','stop','oco']){
              const {m,a,k}=make();let r;
              if(kind==='oco'){
                const base={code:k.code,side:'buy',type:'market',qty:100,operation:'open',creditType:'system'};
                const filled=product==='cash'?a.place(base,m):a.placeCredit(base,m);
                check(filled.ok,product+' OCO holding setup');
                const p=a.creditPositions[0];
                r=a.placeAdvanced({product,code:k.code,side:'sell',type:'oco',qty:100,ocoLimit:k.upper,ocoStop:k.lower,operation:'close',creditType:'system',positionId:p&&p.id},m);
              }else{
                if(kind==='market')m.sec=T.AM_CLOSE+1;
                const spec={product,code:k.code,side:'buy',type:kind,qty:100,stopPrice:k.upper,operation:'open',creditType:'system'};
                r=kind==='stop'?a.placeAdvanced(spec,m):(product==='cash'?a.place(spec,m):a.placeCredit(spec,m));
              }
              check(r.ok,product+' '+kind+' setup');if(!r.ok)continue;
              const before=snap(a),v=a.amendLimitOrder(product,r.order.id,stepPrice(k.lower,1,k.table),m,a.limitAmendmentKey(product,r.order.id));
              check(!v.ok&&snap(a)===before,product+' '+kind+' amendment rejects without mutation');
            }
            for(const sec of [T.PRE_CLOSE,T.PM_CLOSE]){
              const {m,a,k}=make(),r=ordinary(a,m,k,product);check(r.ok,product+' close setup');if(!r.ok)continue;
              m.sec=sec;const before=snap(a),v=a.amendLimitOrder(product,r.order.id,stepPrice(k.lower,1,k.table),m,a.limitAmendmentKey(product,r.order.id));
              check(!v.ok&&snap(a)===before,product+' closing restriction rejects '+sec);
            }
          }
        ''')

    def test_i_stock_tabs_keep_selection_and_empty_states(self):
        self.route('chart');code=self.selected_code()
        self.view('company');self.assertIn(code,self.page.locator('#company-code').inner_text())
        self.view('news');self.assertIn(code,self.selected_code())
        self.page.locator('#stock-news-scope').select_option('direct')
        linked=self.page.locator('#stock-news-list [data-news-stock-code]').evaluate_all('es=>es.map(e=>e.dataset.newsStockCode)')
        self.assertTrue(all(c in code for c in linked),'Scoped direct news includes another stock')
        self.view('hold');self.assertIn(code,self.selected_code())
        self.assertTrue(self.page.locator('#stock-hold-cash-empty').is_visible())
        self.assertTrue(self.page.locator('#stock-hold-credit-empty').is_visible())
        self.view('chart');self.assertIn(code,self.selected_code())
        self.page.locator('#s-next').tap();newcode=self.selected_code();self.assertNotEqual(code,newcode)
        for view in ['company','news','hold','chart']:
            self.view(view);self.assertIn(newcode,self.selected_code())
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),413)

    def test_i_global_corporate_news_opens_its_stock(self):
        self.route('news')
        link=self.page.locator('#news-list [data-news-stock-code]').first
        self.assertGreater(link.count(),0,'Seeded opening market should contain corporate news')
        code=link.get_attribute('data-news-stock-code')
        link.tap()
        self.assertEqual('chart',self.page.locator('body').get_attribute('data-page'))
        self.assertIn(code,self.selected_code())
        self.view('news');self.page.locator('#stock-news-scope').select_option('direct')
        links=self.page.locator('#stock-news-list [data-news-stock-code]')
        self.assertGreater(links.count(),0)
        for value in links.evaluate_all('es=>es.map(e=>e.dataset.newsStockCode)'):self.assertEqual(code,value)
        links.first.tap();self.assertIn(code,self.selected_code())
        self.assertEqual('chart',self.page.locator('body').get_attribute('data-page'))

    def test_i_cash_credit_holdings_actions_and_persistence(self):
        self.route('chart');code=self.selected_code()
        self.buy_market('cash');self.buy_market('credit')
        before=self.account()
        self.route('chart');self.view('hold')
        cash=self.page.locator('#stock-hold-cash');credit=self.page.locator('#stock-hold-credit')
        self.assertIn('100',cash.inner_text());self.assertIn('100',credit.inner_text())
        self.assertFalse(self.page.locator('#stock-hold-cash-empty').is_visible())
        self.assertFalse(self.page.locator('#stock-hold-credit-empty').is_visible())
        cash.locator('.stock-cash-sell').tap()
        self.assertEqual('cash',self.page.locator('input[name="product"]:checked').input_value())
        self.assertEqual('sell',self.page.locator('input[name="oside"]:checked').input_value())
        self.route('chart');self.view('hold');credit.locator('[data-credit-close]').first.tap()
        self.assertEqual('credit',self.page.locator('input[name="product"]:checked').input_value())
        self.assertEqual('close',self.page.locator('input[name="credit-operation"]:checked').input_value())
        self.save_reload();self.assertEqual(before,self.account())
        self.route('chart');self.view('hold');self.assertIn(code,self.selected_code())
        self.assertFalse(self.page.locator('#stock-hold-cash-empty').is_visible())
        self.assertFalse(self.page.locator('#stock-hold-credit-empty').is_visible())
        self.view('chart');self.page.locator('#s-next').tap();self.view('hold')
        self.assertTrue(self.page.locator('#stock-hold-cash-empty').is_visible())
        self.assertTrue(self.page.locator('#stock-hold-credit-empty').is_visible())

if __name__=='__main__':
    print('Screenshots:',ARTIFACTS,flush=True)
    unittest.main(argv=[sys.argv[0]]+remaining,verbosity=2)
