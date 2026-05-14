/**
 * ACL Rehab Coach - Bridge Mode Entry Point
 * 
 * This entry point uses Node.js only for WhatsApp transport (Baileys),
 * while delegating all coaching logic to the Python backend.
 */

import dotenv from 'dotenv';
import express from 'express';
import { WhatsAppBot } from './whatsapp-bot.js';
import { BridgeClient } from './bridge-client.js';

// Load environment variables
dotenv.config();

class ACLRehabCoachBridge {
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

    // Initialize Express Server
    this.app = express();
    this.app.use(express.json());
    
    // Health endpoint
    this.app.get('/health', (req, res) => {
      const connected = this.whatsapp.isConnected && this.whatsapp.isConnected();
      if (connected) {
        return res.status(200).json({ status: 'ok', provider: process.env.LLM_PROVIDER || 'unknown', model: process.env.LLM_MODEL || 'unknown' });
      }
      return res.status(503).json({ status: 'disconnected' });
    });

    // Set up the push endpoint
    this.app.post('/api/send-message', async (req, res) => {
      const { userId, messageText, whatsapp_payload, context } = req.body;
      if (!userId) {
        return res.status(400).json({ error: 'Missing userId' });
      }
      if (!messageText && !whatsapp_payload) {
        return res.status(400).json({ error: 'Missing messageText or whatsapp_payload' });
      }

      try {
        const payload = whatsapp_payload ? { text: messageText, whatsapp_payload } : messageText;
        const sendResult = await this.whatsapp.sendMessage(userId, payload, context);
        // sendResult should include the stanzaId or message id from Baileys
        const stanzaId = sendResult?.stanzaId || sendResult?.id || null;
        res.status(200).json({ success: true, stanzaId });
      } catch (error) {
        console.error('[BRIDGE] Error sending push message:', error);
        res.status(500).json({ error: error.message });
      }
    });

    // Inbound webhook from WhatsApp library (internal listener will call handleIncomingMessage)
    // Expose a lightweight endpoint for testing and for external forwards
    this.app.post('/api/inbound', async (req, res) => {
      const { from, text, contextInfo } = req.body;
      try {
        // Normalize payload and forward to Python bridge
        const payload = {
          user_id: from,
          message_text: text,
          context: contextInfo || null,
        };
        // Forward to Python bridge
        const result = await this.bridge.client.post('/message', payload);
        res.status(200).json(result.data);
      } catch (error) {
        console.error('[BRIDGE] Error forwarding inbound message:', error);
        res.status(500).json({ error: error.message });
      }
    });
  }

  async handleMessage(userId, messageText, media, context = null) {
    console.log(`[BRIDGE] Processing message from ${userId}`);

    // Send typing indicator
    await this.whatsapp.sendTyping(userId, true);

    try {
      // Forward message to Python coach
      const result = await this.bridge.sendMessage(userId, messageText, media, context);

      await this.whatsapp.sendTyping(userId, false);

      if (result.success) {
        return { text: result.response, whatsapp_payload: result.whatsapp_payload };
      } else {
        console.error(`[BRIDGE] Error from Python coach: ${result.error}`);
        return { text: result.response || '❌ I apologize, but I encountered a technical issue. Please try sending your message again.' };
      }

    } catch (error) {
      console.error('[BRIDGE] Error handling message:', error);
      await this.whatsapp.sendTyping(userId, false);
      return { text: '❌ I apologize, but I encountered a technical issue. Please try sending your message again.' };
    }
  }

  async start() {
    console.log('🦞 ACL Rehab Coach (Bridge Mode) Starting...\n');

    // Wait for Python bridge to be ready
    console.log('[BRIDGE] Waiting for Python backend...');
    const bridgeReady = await this.bridge.waitForBridge(30, 2000);

    if (!bridgeReady) {
      console.error('❌ Python bridge not available. Please start the Python service first.');
      console.error('   Run: python -m app.main');
      process.exit(1);
    }

    const health = await this.bridge.healthCheck();
    console.log(`[BRIDGE] Connected to Python coach`);
    console.log(`   Provider: ${health.provider}`);
    console.log(`   Model: ${health.model}\n`);

    // Connect WhatsApp
    await this.whatsapp.connect();

    // Start Express server
    const port = process.env.BRIDGE_PORT || 3000;
    this.server = this.app.listen(port, () => {
      console.log(`\n🚀 [BRIDGE] Express push server listening on port ${port}`);
    });

    console.log('\n✅ ACL Rehab Coach (Bridge Mode) is running!');
    console.log('   WhatsApp -> Node.js -> Python Coach');
    console.log('   Waiting for WhatsApp messages...\n');
  }

  async stop() {
    console.log('\n🛑 Shutting down ACL Rehab Coach (Bridge Mode)...');
    if (this.server) {
      this.server.close();
      console.log('[BRIDGE] Express server closed');
    }
    await this.whatsapp.disconnect();
    console.log('✅ Shutdown complete');
    process.exit(0);
  }
}

// Start the application
const coach = new ACLRehabCoachBridge();

// Handle graceful shutdown
process.on('SIGINT', () => coach.stop());
process.on('SIGTERM', () => coach.stop());

// Start the bot
coach.start().catch(error => {
  console.error('❌ Fatal error starting ACL Rehab Coach:', error);
  process.exit(1);
});

export default ACLRehabCoachBridge;
