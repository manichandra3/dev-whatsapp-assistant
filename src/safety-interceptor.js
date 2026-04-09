/**
 * Safety Interceptor - Red Flag Detection System
 * 
 * This module implements the deterministic safety rule engine that intercepts
 * all incoming messages BEFORE LLM processing. If red flag keywords are detected,
 * it bypasses the AI and returns a hardcoded emergency response.
 */

export class SafetyInterceptor {
  constructor() {
    // Critical medical emergency keywords
    this.redFlagPatterns = [
      // DVT/Blood clot indicators
      /\b(calf\s+pain|calf\s+swelling|calf\s+tenderness)\b/i,
      
      // Infection indicators
      /\b(fever|high\s+fever|temperature|chills|infection|pus|discharge|oozing)\b/i,
      
      // Graft failure indicators
      /\b(loud\s+pop|popping\s+sound|heard\s+pop|graft\s+failure|knee\s+gave\s+out)\b/i,
      
      // Severe swelling
      /\b(huge\s+swelling|massive\s+swelling|extreme\s+swelling|swelling\s+worse|excessive\s+swelling)\b/i,
      
      // Severe pain
      /\b(severe\s+pain|unbearable\s+pain|excruciating|pain\s+level\s+(9|10)|worst\s+pain)\b/i,
      
      // Neurological symptoms
      /\b(numbness|tingling|loss\s+of\s+feeling|can't\s+feel|nerve\s+damage)\b/i,
      
      // Cardiovascular/respiratory emergencies
      /\b(chest\s+pain|breathing\s+difficult|shortness\s+of\s+breath|can't\s+breathe)\b/i,
      
      // Circulation issues
      /\b(foot\s+cold|foot\s+blue|toes\s+blue|no\s+pulse)\b/i
    ];

    this.emergencyResponse = `
🚨 **MEDICAL ALERT** 🚨

I've detected symptoms that require IMMEDIATE medical attention. 

**DO NOT WAIT - CONTACT YOUR SURGEON OR GO TO THE ER NOW**

⚠️ Potential emergency indicators detected:
- Deep vein thrombosis (blood clot)
- Infection
- Graft failure
- Severe complications

📞 **Actions to take RIGHT NOW:**
1. Call your surgeon's emergency line
2. If unavailable, go to the Emergency Room
3. If experiencing chest pain or breathing difficulty, call emergency services (911)

⏰ **Time is critical** - these symptoms can indicate life-threatening complications.

This is an automated safety alert. I cannot provide medical diagnosis or treatment. Please seek immediate professional medical care.
    `.trim();
  }

  /**
   * Check message for red flag keywords
   * @param {string} message - The incoming user message
   * @returns {Object} - { hasRedFlag: boolean, response: string|null }
   */
  checkMessage(message) {
    if (!message || typeof message !== 'string') {
      return { hasRedFlag: false, response: null };
    }

    const lowerMessage = message.toLowerCase();

    for (const pattern of this.redFlagPatterns) {
      if (pattern.test(lowerMessage)) {
        console.warn(`[SAFETY] Red flag detected in message: "${message}"`);
        console.warn(`[SAFETY] Matched pattern: ${pattern}`);
        
        return {
          hasRedFlag: true,
          response: this.emergencyResponse,
          matchedPattern: pattern.toString()
        };
      }
    }

    return { hasRedFlag: false, response: null };
  }

  /**
   * Get all red flag patterns (for testing/debugging)
   * @returns {Array<RegExp>}
   */
  getPatterns() {
    return this.redFlagPatterns;
  }

  /**
   * Test a specific pattern
   * @param {string} text - Text to test
   * @param {RegExp} pattern - Pattern to test against
   * @returns {boolean}
   */
  testPattern(text, pattern) {
    return pattern.test(text.toLowerCase());
  }
}

export default SafetyInterceptor;
