#!/usr/bin/env node
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../modules/common/functions/MonitorResolution.js'), 'utf8');
const context = vm.createContext({});
vm.runInContext(source.replace(/^\.pragma library\s*/u, ''), context);
const resolution = context.resolution;
const output = {current_mode: 0, modes: [
    {width: 2560, height: 1600, refresh_rate: 165004},
    {width: 1920, height: 1200, refresh_rate: 165004}
], logical: {width: 2048, height: 1280, scale: 1.25}};
const original = JSON.stringify(output);
assert.equal(resolution(output, {width: 2048, height: 1280, devicePixelRatio: 1.25}), '2560×1600');
assert.equal(resolution(output, {width: 1707, height: 1067, devicePixelRatio: 1.5}), '2560×1600');
assert.equal(resolution({...output, current_mode: 1}), '1920×1200');
assert.equal(resolution({...output, logical: {width: 1280, height: 2048, transform: '90'}}), '2560×1600');
assert.equal(resolution({...output, current_mode: null}, {width: 1707, height: 1067}), '');
assert.equal(resolution({...output, current_mode: 99}), '');
assert.equal(resolution({...output, modes: []}), '');
assert.equal(resolution(null, {width: 1920, height: 1080, devicePixelRatio: 2}), '3840×2160');
assert.equal(resolution(null, {width: 2560, height: 1440}), '2560×1440');
assert.equal(resolution(null, null), '');
assert.equal(JSON.stringify(output), original);
console.log('PASS physical modes including index zero, scaling, rotation, disabled outputs and Qt fallback');
