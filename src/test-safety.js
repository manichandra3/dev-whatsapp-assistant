/**
 * Safety Interceptor Test Suite
 * 
 * Run: npm test
 */

import { SafetyInterceptor } from './safety-interceptor.js';

console.log('🧪 Testing Safety Interceptor\n');
console.log('=' . repeat(60));

const safety = new SafetyInterceptor();

// Test cases
const testCases = [
  {
    name: 'Normal message',
    message: 'My pain level is 4 today and swelling is about the same',
    shouldTrigger: false
  },
  {
    name: 'Calf pain (DVT indicator)',
    message: 'I have some calf pain in my leg',
    shouldTrigger: true
  },
  {
    name: 'Fever (infection indicator)',
    message: 'I think I have a fever, feeling really hot',
    shouldTrigger: true
  },
  {
    name: 'Loud pop (graft failure)',
    message: 'I heard a loud pop in my knee during exercise',
    shouldTrigger: true
  },
  {
    name: 'Huge swelling',
    message: 'The swelling is huge and getting worse',
    shouldTrigger: true
  },
  {
    name: 'Severe pain',
    message: 'I have severe pain that won\'t go away',
    shouldTrigger: true
  },
  {
    name: 'Numbness',
    message: 'My foot feels numb and tingly',
    shouldTrigger: true
  },
  {
    name: 'Chest pain',
    message: 'Having chest pain and hard to breathe',
    shouldTrigger: true
  },
  {
    name: 'Pain level 9',
    message: 'My pain level is 9 out of 10',
    shouldTrigger: true
  },
  {
    name: 'Normal high pain',
    message: 'Pain is about 6 today',
    shouldTrigger: false
  },
  {
    name: 'Infection mention',
    message: 'Worried about infection, seeing some discharge',
    shouldTrigger: true
  },
  {
    name: 'General swelling',
    message: 'Still have some swelling but it\'s better',
    shouldTrigger: false
  }
];

let passed = 0;
let failed = 0;

for (const test of testCases) {
  const result = safety.checkMessage(test.message);
  const success = result.hasRedFlag === test.shouldTrigger;
  
  if (success) {
    console.log(`✅ PASS: ${test.name}`);
    console.log(`   Message: "${test.message}"`);
    console.log(`   Expected trigger: ${test.shouldTrigger}, Got: ${result.hasRedFlag}`);
    passed++;
  } else {
    console.log(`❌ FAIL: ${test.name}`);
    console.log(`   Message: "${test.message}"`);
    console.log(`   Expected trigger: ${test.shouldTrigger}, Got: ${result.hasRedFlag}`);
    if (result.matchedPattern) {
      console.log(`   Matched pattern: ${result.matchedPattern}`);
    }
    failed++;
  }
  console.log('');
}

console.log('=' . repeat(60));
console.log(`\n📊 Test Results:`);
console.log(`   Total: ${testCases.length}`);
console.log(`   ✅ Passed: ${passed}`);
console.log(`   ❌ Failed: ${failed}`);
console.log(`   Success Rate: ${((passed / testCases.length) * 100).toFixed(1)}%\n`);

if (failed > 0) {
  console.log('⚠️  Some tests failed. Review red flag patterns.');
  process.exit(1);
} else {
  console.log('🎉 All tests passed! Safety interceptor working correctly.');
  process.exit(0);
}
