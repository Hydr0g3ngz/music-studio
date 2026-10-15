const test = require('node:test');
const assert = require('node:assert/strict');
const {AudioAssetTransport} = require('../src/music_studio/ui/static/transport.js');

function media() {
  return {src:'', currentTime:0, paused:true, loads:0, pauses:0,
    load(){this.loads++;this.currentTime=0;}, pause(){this.paused=true;this.pauses++;},
    removeAttribute(name){if(name==='src')this.src='';}};
}
test('repeated UI refreshes preserve playback position and do not reload a pinned asset',()=>{
  const audio=media(), player=new AudioAssetTransport(audio);
  assert.equal(player.bind('project1:source','/audio/source'),true);
  audio.paused=false;audio.currentTime=31.25;
  for(let i=0;i<100;i++)assert.equal(player.bind('project1:source','/audio/source'),false);
  assert.equal(audio.loads,1);assert.equal(audio.pauses,1);
  assert.equal(audio.currentTime,31.25);assert.equal(audio.paused,false);
});
test('new previews and different projects load once each',()=>{
  const audio=media(), player=new AudioAssetTransport(audio);
  player.bind('project1:source','/p1/source');
  player.bind('project1:candidate:abc','/p1/candidate/abc');
  player.bind('project2:source','/p2/source');
  assert.equal(audio.loads,3);assert.equal(audio.src,'/p2/source');
});
test('same-asset retry is explicit and clearing a deleted project releases its media',()=>{
  const audio=media(), player=new AudioAssetTransport(audio);
  player.bind('p1:source','/p1/source');
  player.bind('p1:source','/p1/source',{retry:true});
  assert.equal(audio.loads,2);
  player.clear();assert.equal(audio.src,'');assert.equal(player.key,null);
  player.bind('p1:source','/p1/source');assert.equal(audio.loads,4);
});
