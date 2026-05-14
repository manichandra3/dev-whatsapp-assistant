/**
 * Bridge Client - HTTP Client for Python Coach
 * 
 * This module provides a client for communicating with the Python
 * FastAPI bridge that handles all coaching logic.
 */

/**
 * Bridge client for communicating with Python coach service.
 */
export class BridgeClient {
  constructor(baseUrl = 'http://127.0.0.1:8000') {
    this.baseUrl = baseUrl;
    this.timeout = 60000; // 60 second timeout for LLM calls
  }

  /**
   * Send a message to the Python coach and get a response.
   * @param {string} userId - WhatsApp user ID
   * @param {string} messageText - The message content
   * @returns {Promise<{success: boolean, response: string|null, error: string|null}>}
   */
  async sendMessage(userId, messageText, media = null) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const hasMedia = media && media.buffer;
      const headers = {};
      let body;

      if (hasMedia) {
        const formData = new FormData();
        formData.append('user_id', userId);
        formData.append('message_text', messageText || '');
        if (media.caption) {
          formData.append('media_caption', media.caption);
        }
        formData.append(
          'media',
          new Blob([media.buffer], { type: media.mimeType || 'image/jpeg' }),
          media.fileName || 'image.jpg'
        );
        body = formData;
      } else {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify({
          user_id: userId,
          message_text: messageText,
        });
      }

      const response = await fetch(`${this.baseUrl}/message`, {
        method: 'POST',
        headers,
        body,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`[BRIDGE] HTTP error: ${response.status} - ${errorText}`);
        return {
          success: false,
          response: '❌ I apologize, but I encountered a technical issue. Please try sending your message again.',
          error: `HTTP ${response.status}: ${errorText}`,
        };
      }

      const data = await response.json();
      return data;

    } catch (error) {
      clearTimeout(timeoutId);

      if (error.name === 'AbortError') {
        console.error('[BRIDGE] Request timed out');
        return {
          success: false,
          response: '❌ The request took too long. Please try again.',
          error: 'Request timeout',
        };
      }

      console.error('[BRIDGE] Error sending message:', error);
      return {
        success: false,
        response: '❌ I apologize, but I encountered a technical issue. Please try sending your message again.',
        error: error.message,
      };
    }
  }

  /**
   * Check if the Python bridge is healthy.
   * @returns {Promise<{healthy: boolean, provider: string|null, model: string|null}>}
   */
  async healthCheck() {
    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      });

      if (!response.ok) {
        return { healthy: false, provider: null, model: null };
      }

      const data = await response.json();
      return {
        healthy: data.status === 'healthy',
        provider: data.provider,
        model: data.model,
      };

    } catch (error) {
      console.error('[BRIDGE] Health check failed:', error);
      return { healthy: false, provider: null, model: null };
    }
  }

  /**
   * Wait for the Python bridge to become healthy.
   * @param {number} maxRetries - Maximum number of retries
   * @param {number} retryDelay - Delay between retries in milliseconds
   * @returns {Promise<boolean>}
   */
  async waitForBridge(maxRetries = 30, retryDelay = 1000) {
    for (let i = 0; i < maxRetries; i++) {
      const health = await this.healthCheck();
      if (health.healthy) {
        console.log(`[BRIDGE] Connected to Python coach (${health.provider}/${health.model})`);
        return true;
      }

      console.log(`[BRIDGE] Waiting for Python bridge... (${i + 1}/${maxRetries})`);
      await new Promise(resolve => setTimeout(resolve, retryDelay));
    }

    console.error('[BRIDGE] Failed to connect to Python bridge after max retries');
    return false;
  }
}

export default BridgeClient;
