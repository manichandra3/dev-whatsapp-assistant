/**
 * Developer WhatsApp Assistant - Main Application
 * 
 * Coordinates WhatsApp bot, SQLite memory, and LLM Intent Routing.
 */

import dotenv from 'dotenv';
import { WhatsAppBot } from './whatsapp-bot.js';
import { DatabaseManager } from './database.js';
import { LLMProvider } from './llm-provider.js';

// Load environment variables
dotenv.config();

class DevAssistant {
  constructor() {
    // Initialize components
    this.db = new DatabaseManager(process.env.DATABASE_PATH);
    
    // Initialize LLM
    this.llm = new LLMProvider(
      process.env.LLM_PROVIDER || 'openai',
      process.env.LLM_MODEL || 'gpt-4o',
      this.getLLMApiKey()
    );

    // Initialize WhatsApp bot
    this.whatsapp = new WhatsAppBot(
      process.env.WHATSAPP_SESSION_PATH || './whatsapp_session',
      this.handleMessage.bind(this)
    );
  }

  getLLMApiKey() {
    const provider = (process.env.LLM_PROVIDER || 'openai').toLowerCase();
    
    switch (provider) {
      case 'openai':
        return process.env.OPENAI_API_KEY;
      case 'anthropic':
        return process.env.ANTHROPIC_API_KEY;
      case 'google':
        return process.env.GOOGLE_API_KEY;
      default:
        throw new Error(`No API key found for provider: ${provider}`);
    }
  }

  async handleMessage(userId, messageText) {
    console.log(`[ASSISTANT] Processing message from ${userId}`);

    // STEP 1: Ensure user exists
    this.db.getOrCreateUser(userId);

    // STEP 2: Send typing indicator
    await this.whatsapp.sendTyping(userId, true);

    try {
      // 1. Save user message to SQLite
      this.db.saveMessage(userId, 'user', messageText);

      // 2. Fetch context from SQLite
      const recentMessages = this.db.getRecentMessages(userId, 10);
      
      // Build messages for LLM
      const messages = [
        { role: 'system', content: this.llm.getSystemPrompt() },
        ...recentMessages
      ];

      // 3. Call LLM
      const response = await this.llm.chat(messages);

      let parsedJSON = response.parsedJSON;

      // 4. Parse output with Silent Catch
      if (!parsedJSON || !this._isValidIntent(parsedJSON)) {
        console.warn(`[ASSISTANT] Failed to parse valid JSON. Raw output: ${response.content}`);
        parsedJSON = {
          intent: 'general_chat',
          topic: 'system_fallback',
          metadata: {
            response_text: 'I had a bit of trouble parsing that request. Could you rephrase it?'
          }
        };
      }

      // 5. Save assistant JSON response to SQLite
      const jsonStr = JSON.stringify(parsedJSON);
      this.db.saveMessage(userId, 'assistant', jsonStr);

      // 6. Log parsed intent
      this.db.logIntent(
        userId,
        messageText,
        parsedJSON.intent || 'general_chat',
        parsedJSON.topic || 'unknown',
        parsedJSON.metadata || {}
      );

      await this.whatsapp.sendTyping(userId, false);
      return jsonStr;

    } catch (error) {
      console.error('[ASSISTANT] Error processing message:', error);
      
      const fallback = {
        intent: 'general_chat',
        topic: 'system_error',
        metadata: {
          response_text: 'I encountered an internal error. Please try again.'
        }
      };

      await this.whatsapp.sendTyping(userId, false);
      return JSON.stringify(fallback);
    }
  }

  _isValidIntent(data) {
    if (!data || typeof data !== 'object') return false;

    const requiredKeys = ['intent', 'topic', 'metadata'];
    for (const key of requiredKeys) {
      if (!(key in data)) return false;
    }

    const validIntents = [
      'schedule_task', 'execute_code', 'debug_code',
      'summarize_link', 'log_expense', 'general_chat'
    ];

    if (!validIntents.includes(data.intent)) return false;

    return true;
  }

  async start() {
    console.log('🤖 Dev Assistant Starting...\n');
    console.log(`LLM Provider: ${process.env.LLM_PROVIDER || 'openai'}`);
    console.log(`Model: ${process.env.LLM_MODEL || 'gpt-4o'}`);
    console.log(`Database: ${process.env.DATABASE_PATH || './data/dev_assistant.db'}\n`);
    
    await this.whatsapp.connect();
    
    console.log('\n✅ Dev Assistant is running!');
    console.log('   Waiting for WhatsApp messages...\n');
  }

  async stop() {
    console.log('\n🛑 Shutting down Dev Assistant...');
    await this.whatsapp.disconnect();
    this.db.close();
    console.log('✅ Shutdown complete');
    process.exit(0);
  }
}

// Start the application
const coach = new DevAssistant();

// Handle graceful shutdown
process.on('SIGINT', () => coach.stop());
process.on('SIGTERM', () => coach.stop());

// Start the bot
coach.start().catch(error => {
  console.error('❌ Fatal error starting Dev Assistant:', error);
  process.exit(1);
});

export default DevAssistant;
