const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=fs.readFileSync(path.join(__dirname,'..','..','results','reporting','X5_RetailHero_经营分析数据看板.html'),'utf8');
const match=html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match,'inline dashboard code exists');
new vm.Script(match[1]);
const elements={};
const element=id=>elements[id]??(elements[id]={innerHTML:'',textContent:'',style:{},onclick:null,showModal(){this.open=true},close(){this.open=false}});
const context=vm.createContext({
  document:{getElementById:element,querySelectorAll:()=>[],createElement:()=>({click(){}})},
  location:{hash:'#overview'},window:{addEventListener(){}},
  URL:{createObjectURL:()=>'',revokeObjectURL(){}},Blob,
  setTimeout:()=>0,console,
});
vm.runInContext(match[1],context);
const read=expr=>vm.runInContext(expr,context);
const render=id=>{context.location.hash='#'+id;read('render()');return element('app').innerHTML};
for(const id of ['overview','customers','stores','experiment','strategy']){
  const page=render(id);
  assert.match(page,/<h1 class="page-title">/);
  assert.ok(page.length>1000,id);
  assert.ok(!page.includes('NaN'),id);
}
let page=render('overview');
assert.match(page,/400,162/);
assert.match(page,/120,022/);
assert.match(page,/\+0\.29/);
assert.match(page,/尚未确认/);
read("state.segment=segments[0];state.recency='全部'");
page=render('customers');
assert.doesNotMatch(page,/class="value">120,022/);
read("state.segment='全部客群';state.recency='全部'");
page=render('customers');
assert.match(page,/class="value">120,022/);
read("state.start='2019-01-01';state.end='2019-01-31';state.store='其他门店'");
page=render('stores');
assert.match(page,/31<small>天<\/small>/);
read("state.sample='验证集';state.reach=5");
page=render('strategy');
assert.match(page,/验证集 · 覆盖5%客户/);
read("state.reach=100");
page=render('strategy');
assert.match(page,/验证集 · 覆盖100%客户/);
assert.match(page,/固定30%覆盖/);
assert.deepEqual(Array.from(read('[...new Set(D.Curves.map(r=>r.reach_pct))].sort((a,b)=>a-b)')).slice(0,3),[5,10,15]);
console.log('PASS: inline JS syntax, five pages, source KPIs, business conclusions, customer/store/strategy filters');
