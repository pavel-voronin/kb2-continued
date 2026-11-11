// Shared by the release packager and the local dev server.
const fs=require('node:fs'),path=require('node:path');
const {zipSync,unzipSync}=require('fflate');
module.exports=function gameBundle(gameDir,classic) {
const game={};
for(const file of fs.readdirSync(gameDir)) {
  if(/^(KB2\.EXE|KB2\.FNT|\w+\.PIC)$/i.test(file))game[file.toUpperCase()]=new Uint8Array(fs.readFileSync(path.join(gameDir,file)));
}
const required=Object.keys(unzipSync(classic)).filter(name=>/\.(EXE|FNT|PIC)$/i.test(name));
for(const name of required)if(!game[name])throw new Error('Incomplete DOS release: '+name);
game['.jsdos/dosbox.conf']=Buffer.from('[dosbox]\nmachine=ega\nmemsize=16\n[cpu]\ncore=normal\ncputype=286\ncycles=fixed 3000\n[render]\naspect=false\nscaler=none\n[mixer]\nrate=44100\nprebuffer=0\n[dos]\nxms=false\nems=false\numb=false\n[autoexec]\n@echo off\nmount c .\nc:\nKB2.EXE\nexit\n');
  return {game,archive:zipSync(game)};
};
