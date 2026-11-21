/* Exercise the actual embedded JS with a minimal DOM event fixture. This does not render a page. */
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, dirname} from 'node:path';
import vm from 'node:vm';

const folder = resolve(dirname(fileURLToPath(import.meta.url)), 'packet');
function element(tag = 'div') {
  const node = {tag, children:[], handlers:{}, style:{}, value:'', textContent:'', checked:false, hidden:false};
  node.descendants = () => node.children.flatMap(child => [child, ...child.descendants()]);
  node.querySelectorAll = query => node.descendants().filter(child => query === ':checked' ? child.checked : child.tag === query);
  node.querySelector = query => node.querySelectorAll(query)[0];
  node.addEventListener = (name, callback) => { node.handlers[name] = callback; };
  node.append = (...children) => node.children.push(...children);
  node.replaceChildren = () => { node.children = []; };
  node.focus = () => {};
  node.remove = () => {};
  node.click = () => {};
  return node;
}
async function check(file) {
  const html = readFileSync(resolve(folder, file), 'utf8');
  const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)];
  assert.equal(scripts.length, 2);
  assert.match(html, /name="viewport" content="width=device-width, initial-scale=1"/);
  const ids = Object.fromEntries([...html.matchAll(/<(\w+)\b[^>]*\bid="([\w-]+)"[^>]*>/g)].map(m => [m[2],element(m[1])]));
  const doc = element('document');
  doc.createElement = element;
  doc.createTextNode = text => Object.assign(element('text'), {textContent:text});
  doc.getElementById = id => ids[id] || ids.facts.descendants().find(item => item.id === id);
  doc.body = element('body');
  ids.handoff.append(element('legend'));
  ids.payload.textContent = scripts[0][2];
  const emitted = [];
  const url = {createObjectURL:blob => { emitted.push(blob); return 'blob:test'; }, revokeObjectURL:()=>{}};
  const window = element('window'); window.scrollTo = () => {};
  let now = 500;
  vm.runInNewContext(scripts[1][2], {document:doc, window, performance:{now:()=>now}, URL:url, Blob, setTimeout:f=>f()});
  const submit = form => ids[form].handlers.submit({preventDefault:()=>{}});
  ids.reader.value = 'R-000000000000'; ids.eligible.checked = true;
  submit('start-form');
  for (let i=1;i<=2;i++) {
    assert.equal(ids.progress.textContent, `報告 ${i} / 2`);
    assert.equal(ids.facts.querySelectorAll('input').length,3);
    for (const item of ids.facts.querySelectorAll('input')) { assert.equal(item.required,true); item.value = ' '; }
    submit('answer-form'); assert.ok(ids.error.textContent);
    for (const item of ids.facts.querySelectorAll('input')) item.value='技術試験のみ';
    assert.equal(ids.choices.querySelectorAll('input').length,5);
    ids.choices.querySelectorAll('input')[4].checked=true; ids.useful.value='3';
    now+=7; doc.hidden=true; doc.handlers.visibilitychange();
    now+=11; doc.hidden=false; doc.handlers.visibilitychange();
    now+=13; submit('answer-form');
  }
  assert.equal(ids.trial.hidden,true); assert.equal(ids.done.hidden,false);
  ids.download.handlers.click();
  assert.equal(emitted.length,1);
  const raw=await emitted[0].text(); assert.equal(raw,ids.copy.value);
  const data=JSON.parse(raw); assert.equal(data.return_type,'mechanical_test'); assert.equal(data.eligible,false);
  assert.equal(data.form+'.html', file); assert.equal(data.tasks.length,2);
  for (const task of data.tasks) { assert.deepEqual(task.visible_intervals_ms,[0,7,18,31]); assert.equal(task.handoff,4); }
  return file;
}
const files=readdirSync(folder).filter(name => name.endsWith('.html')).sort();
const checked=[];
for (const file of files) checked.push(await check(file));
console.log(JSON.stringify({tested:'embedded JS with a DOM fixture; no browser rendering', packets:checked, human_returns_created:0},null,2));
