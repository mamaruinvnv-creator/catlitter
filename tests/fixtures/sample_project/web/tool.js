import { usedThing } from './other.js';
import unusedThing from './legacy.js';
const axios = require('axios');

function called() {
  return usedThing();
}

function neverCalled() {
  return 42;
}

// const oldVar = 1;
// oldVar = oldVar + 2;
// console.log(oldVar);

function run() {
  console.log("debug here");
  debugger;
  return called();
}

run();
