const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {create, en} = require('../src/music_studio/ui/static/i18n.js');

test('language preference is persisted and overrides browser language', () => {
  const saved = new Map();
  const storage = {getItem: key => saved.get(key), setItem: (key,value) => saved.set(key,value)};
  const i18n = create({storage, browserLanguage: 'zh-TW'});
  assert.equal(i18n.language, 'zh');
  i18n.setLanguage('en');
  assert.equal(i18n.t('播放'), 'Play');
  assert.equal(create({storage, browserLanguage: 'zh-CN'}).language, 'en');
  assert.equal(i18n.t('删除歌曲 {title}', {title: '我的歌 <song>'}), 'Delete song 我的歌 <song>');
  i18n.setLanguage('zh');
  assert.equal(i18n.t('删除歌曲 {title}', {title: 'A Song'}), '删除歌曲 A Song');
});

test('storage denial and unknown lyrics do not break translation', () => {
  const i18n = create({storage: {getItem() {throw Error('blocked');}, setItem() {throw Error('blocked');}}});
  assert.equal(i18n.t('用户唱出的任意一句歌词'), '用户唱出的任意一句歌词');
  const status = i18n.t('歌词已保存，导出文件已同步更新');
  i18n.setLanguage('zh');
  assert.equal(i18n.retranslate(status), '歌词已保存，导出文件已同步更新');
  assert.ok(Object.values(en).every(value => typeof value === 'string' && value.length));
});

test('actual language redraw preserves playback, version and unsaved editor input without requests', () => {
  const app = fs.readFileSync(require.resolve('../src/music_studio/ui/static/app.js'), 'utf8');
  const source = app.slice(app.indexOf('function refreshLanguage()'), app.indexOf('\n$("#ui-language").onchange'));
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, {textContent:'', value:'', open:false});
    return elements.get(id);
  };
  get('lyrics-dialog').open = true;
  get('lyrics-input').value = '尚未保存的修改';
  const state = {job:{has_result:true}, version:'same-version', generation:7, mode:'vocals',
    editingLine:{index:0,id:'line'}, edits:{review:{lines:{}}}, project:{lyrics:{segments:[{text:'原始歌词'}]},melody:{notes:[]}}};
  const player = {ready:true, playing:true, time:12.4, load(){throw Error('reload');}, reset(){throw Error('reset');}};
  const noop = () => {};
  const i18n = create({browserLanguage:'en'});
  vm.runInNewContext(source + '\nrefreshLanguage()', {state,player,t:i18n.t,MusicI18n:i18n,
    document:{getElementById:get},$:key=>get(key.slice(1)), trackNames:{vocals:'人声'},
    renderProjects:noop,renderStatus:noop,renderTrash:noop,renderVersions:noop,renderLyrics:noop,
    drawTimeline:noop,refreshPlayback:noop,updateControls:noop,
    fetch(){throw Error('Unexpected network request');}});
  assert.equal(player.playing,true);
  assert.equal(player.time,12.4);
  assert.equal(state.version,'same-version');
  assert.equal(state.generation,7);
  assert.equal(state.project.lyrics.segments[0].text,'原始歌词');
  assert.equal(get('lyrics-input').value,'尚未保存的修改');
  assert.equal(get('audio-status').textContent,'Listening: Vocals · Space to play / pause');
});
