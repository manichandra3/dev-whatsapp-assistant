/**
 * Dev Assistant - Bridge Mode Entry Point
 * 
 * This entry point uses Node.js only for WhatsApp transport (Baileys),
 * while delegating all assistant logic to the Python backend.
 */

import dotenv from 'dotenv';
import { WhatsAppBot } from './whatsapp-bot.js';
import { BridgeClient } from './bridge-client.js';

// Load environment variables
dotenv.config();

class DevAssistantBridge {
  constructor() {
    // Build bridge URL from environment
    const bridgeHost = process.env.PYTHON_BRIDGE_HOST || '127.0.0.1';
    const bridgePort = process.env.PYTHON_BRIDGE_PORT || '8000';
    const bridgeUrl = `http://${bridgeHost}:${bridgePort}`;

    // Initialize bridge client
    this.bridge = new BridgeClient(bridgeUrl);

    // Initialize WhatsApp bot
    this.whatsapp = new WhatsAppBot(
      process.env.WHATSAPP_SESSION_PATH || './whatsapp_session',
      this.handleMessage.bind(this)
    );
  }

  async handleMessage(userId, messageText) {
    console.log(`[BRIDGE] Processing message from ${userId}`);

    // Send typing indicator
    await this.whatsapp.sendTyping(userId, true);

    try {
      // Forward message to Python brain
      const result = await this.bridge.sendMessage(userId, messageText);

      await this.whatsapp.sendTyping(userId, false);

      if (result.success) {
        return result.response;
      } else {
        console.error(`[BRIDGE] Error from Python brain: ${result.error}`);
        return result.response || '❌ I apologize, but I encountered a technical issue. Please try sending your message again.';
      }

    } catch (error) {
      console.error('[BRIDGE] Error handling message:', error);
      await this.whatsapp.sendTyping(userId, false);
      return '❌ I apologize, but I encountered a technical issue. Please try sending your message again.';
    }
  }

  async start() {
    console.log('🤖 Dev Assistant (Bridge Mode) Starting...\n');

    // Wait for Python bridge to be ready
    console.log('[BRIDGE] Waiting for Python backend...');
    const bridgeReady = await this.bridge.waitForBridge(30, 2000);

    if (!bridgeReady) {
      console.error('❌ Python bridge not available. Please start the Python service first.');
      console.error('   Run: python -m app.main');
      process.exit(1);
    }

    const health = await this.bridge.healthCheck();
    console.log(`[BRIDGE] Connected to Python brain`);
    console.log(`   Provider: ${health.provider}`);
    console.log(`   Model: ${health.model}\n`);

    // Connect WhatsApp
    await this.whatsapp.connect();

    console.log('\n✅ Dev Assistant (Bridge Mode) is running!');
    console.log('   WhatsApp -> Node.js -> Python Brain');
    console.log('   Waiting for WhatsApp messages...\n');
  }

  async stop() {
    console.log('\n🛑 Shutting down Dev Assistant (Bridge Mode)...');
    await this.whatsapp.disconnect();
    console.log('✅ Shutdown complete');
    process.exit(0);
  }
}

// Start the application
const coach = new DevAssistantBridge();

// Handle graceful shutdown
process.on('SIGINT', () => coach.stop());
process.on('SIGTERM', () => coach.stop());

// Start the bot
coach.start().catch(error => {
  console.error('❌ Fatal error starting Dev Assistant:', error);
  process.exit(1);
});

export default DevAssistantBridge;
