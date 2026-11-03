const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../pages/角色卡面板/index.html'), 'utf8');
const scriptStart = html.indexOf('<script>', html.indexOf('bridge-sdk.js')) + '<script>'.length;
const script = html.slice(scriptStart, html.indexOf('</script>', scriptStart));

function element() {
  return {
    value: '', files: [], children: [],
    get textContent() { return this.text || ''; },
    set textContent(value) { this.text = value; this.children = []; },
    appendChild(child) { this.children.push(child); },
  };
}

async function panel(uploadError, initialBindings = [], packageId = 'sample-card') {
  const elements = new Map();
  const calls = [];
  const bindings = new Map(initialBindings.map(binding => [binding.session_id, binding.package_id]));
  const card = { package_id: packageId, display_name: 'Sample', version: '1', stages: 1, events: 0, adult_events: 0 };
  let cards = [card];
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    createElement: element,
  };
  const bridge = {
    ready: async () => {},
    async apiGet(endpoint, params) {
      calls.push({ method: 'GET', endpoint, params });
      if (endpoint === 'cards') return { cards };
      if (endpoint === 'audits') return { audits: [] };
      return {
        states: [],
        bindings: Array.from(bindings, ([session_id, package_id]) => ({ session_id, package_id }))
          .filter(binding => !params?.session_id || binding.session_id === params.session_id),
      };
    },
    async apiPost(endpoint, body) {
      calls.push({ method: 'POST', endpoint, body });
      if (endpoint === 'binding') {
        if (body.package_id === '') bindings.delete(body.session_id);
        else bindings.set(body.session_id, body.package_id);
      }
      if (endpoint === `cards/${packageId}/delete`) {
        if (Array.from(bindings.values()).includes(packageId)) throw new Error('当前会话正在使用该卡，请先解除绑定');
        cards = [];
      }
      return {};
    },
    async upload(endpoint, file) {
      calls.push({ method: 'UPLOAD', endpoint, file });
      if (uploadError) throw uploadError;
      cards = [card];
      return {};
    },
  };
  const context = vm.createContext({ document, window: { AstrBotPluginPage: bridge }, URL, URLSearchParams });
  vm.runInContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  return { elements, calls, document };
}

test('initialization and queries use plugin endpoints without a page prefix', async () => {
  const { elements, calls } = await panel();
  assert.deepEqual(calls.map(call => call.endpoint), ['cards', 'state', 'audits']);
  assert.equal(elements.get('cards').children.length, 1);
  elements.get('sessionId').value = 'bot:FriendMessage:123';
  elements.get('memberId').value = '123';
  await elements.get('queryState').onclick();
  const query = calls.at(-1);
  assert.equal(query.endpoint, 'state');
  assert.equal(query.params.session_id, 'bot:FriendMessage:123');
  assert.equal(query.params.member_id, '123');
});

test('binding posts a JSON object and keeps the session identity intact', async () => {
  const { elements, calls } = await panel();
  elements.get('sessionId').value = 'bot:FriendMessage:123';
  const row = elements.get('cards').children[0];
  await row.children.at(-1).children[0].onclick();
  const binding = calls.find(call => call.method === 'POST');
  assert.equal(binding.endpoint, 'binding');
  assert.equal(binding.body.session_id, 'bot:FriendMessage:123');
  assert.equal(binding.body.package_id, 'sample-card');
});

test('deleting a Chinese package ID passes it to the bridge without pre-encoding', async () => {
  const { elements, calls } = await panel(undefined, [], '示例卡');
  const card = elements.get('cards').children[0];
  card.onclick();
  card.children.at(-1).children[1].onclick();
  await new Promise(resolve => setImmediate(resolve));
  const deletion = calls.find(call => call.method === 'POST');
  assert.equal(deletion.endpoint, 'cards/示例卡/delete');
  assert.equal(deletion.endpoint.includes('%'), false);
});

test('ZIP and JSON uploads pass the selected file to the official upload bridge', async () => {
  const { elements, calls, document } = await panel();
  for (const name of ['character.zip', 'character.json']) {
    const file = { name };
    document.getElementById('file').files = [file];
    await elements.get('uploadForm').onsubmit({ preventDefault() {} });
    const upload = calls.findLast(call => call.method === 'UPLOAD');
    assert.equal(upload.endpoint, 'cards/import');
    assert.equal(upload.file, file);
    assert.equal(elements.get('message').textContent, '导入完成');
    assert.deepEqual(calls.slice(-3).map(call => call.endpoint), ['cards', 'state', 'audits']);
  }
});

test('upload errors show the server message and do not report success', async () => {
  const { elements, calls, document } = await panel(new Error('卡包已存在，拒绝覆盖：sample'));
  document.getElementById('file').files = [{ name: 'character.zip' }];
  await elements.get('uploadForm').onsubmit({ preventDefault() {} });
  assert.equal(elements.get('message').textContent, '导入失败：卡包已存在，拒绝覆盖：sample');
  assert.equal(calls.at(-1).method, 'UPLOAD');
});

test('the only card can be unbound from every session, deleted and reimported', async () => {
  const sessions = ['bot:FriendMessage:123', 'bot:GroupMessage:456'];
  const { elements, calls, document } = await panel(undefined, sessions.map(session_id => ({ session_id, package_id: 'sample-card' })));
  assert.equal(elements.get('bindings').children.length, 2);
  await elements.get('cards').children[0].children.at(-1).children[1].onclick();
  assert.match(elements.get('message').textContent, /删除失败/);

  for (const session of sessions) {
    const row = elements.get('bindings').children[0];
    assert.equal(row.children[0].textContent, session);
    await row.children[2].children[0].onclick();
    const unbind = calls.findLast(call => call.method === 'POST');
    assert.equal(unbind.endpoint, 'binding');
    assert.equal(unbind.body.session_id, session);
    assert.equal(unbind.body.package_id, '');
  }
  assert.equal(elements.get('bindings').children.length, 0);
  assert.equal(elements.get('noBindings').hidden, false);

  await elements.get('cards').children[0].children.at(-1).children[1].onclick();
  assert.equal(elements.get('cards').children.length, 0);
  document.getElementById('file').files = [{ name: 'new-release.zip' }];
  await elements.get('uploadForm').onsubmit({ preventDefault() {} });
  assert.equal(elements.get('cards').children.length, 1);
  assert.equal(elements.get('message').textContent, '导入完成');
});

test('current-session unbinding requires no member or selected card and preserves other bindings', async () => {
  const { elements, calls } = await panel(undefined, [
    { session_id: 'bot:FriendMessage:123', package_id: 'sample-card' },
    { session_id: 'bot:FriendMessage:456', package_id: 'sample-card' },
  ]);
  await elements.get('unbindSession').onclick();
  assert.equal(calls.some(call => call.method === 'POST'), false);
  elements.get('sessionId').value = ' bot:FriendMessage:123 ';
  await elements.get('unbindSession').onclick();
  assert.equal(elements.get('bindings').children.length, 1);
  assert.equal(elements.get('bindings').children[0].children[0].textContent, 'bot:FriendMessage:456');
  assert.match(elements.get('message').textContent, /已解除会话绑定/);
});
