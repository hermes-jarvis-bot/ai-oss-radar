const assert = require('node:assert/strict');
const { sortWatchItems } = require('../app/static/sorting.js');

const items = [
  { full_name: 'automatic-late', manual: false, stars: 90, expires_at: '2026-09-20T00:00:00Z' },
  { full_name: 'pinned-no-expiry', manual: true, stars: 1, expires_at: null },
  { full_name: 'automatic-near', manual: false, stars: 10, expires_at: '2026-09-02T00:00:00Z' },
  { full_name: 'pinned-finite', manual: true, stars: 200, expires_at: '2026-09-01T00:00:00Z' },
  { full_name: 'automatic-no-expiry', manual: false, stars: 300, expires_at: null },
];

const names = sort => sortWatchItems(items, sort).map(item => item.full_name);
assert.deepEqual(names('default'), ['pinned-finite', 'pinned-no-expiry', 'automatic-near', 'automatic-late', 'automatic-no-expiry']);
assert.deepEqual(names('stars-desc'), ['pinned-finite', 'pinned-no-expiry', 'automatic-no-expiry', 'automatic-late', 'automatic-near']);
assert.deepEqual(names('stars-asc'), ['pinned-no-expiry', 'pinned-finite', 'automatic-near', 'automatic-late', 'automatic-no-expiry']);
assert.deepEqual(names('expiry-soonest'), ['pinned-finite', 'pinned-no-expiry', 'automatic-near', 'automatic-late', 'automatic-no-expiry']);
assert.deepEqual(names('expiry-latest'), ['pinned-no-expiry', 'pinned-finite', 'automatic-no-expiry', 'automatic-late', 'automatic-near']);
console.log('sorting tests passed');
