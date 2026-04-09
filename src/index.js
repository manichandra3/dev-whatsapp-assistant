/**
 * ACL Rehab Coach - Main Application
 * 
 * Coordinates WhatsApp bot, safety interceptor, LLM, and tools
 */

import dotenv from 'dotenv';
import { WhatsAppBot } from './whatsapp-bot.js';
import { SafetyInterceptor } from './safety-interceptor.js';
import { DatabaseManager } from './database.js';
import { ACLRehabTools } from './tools.js';
import { LLMProvider } from './llm-provider.js';

// Load environment variables
dotenv.config();

class ACLRehabCoach {
  constructor() {
    this.conversations = new Map(); // Store conversation history per user
    
    // Initialize components
    this.safety = new SafetyInterceptor();
    this.db = new DatabaseManager(process.env.DATABASE_PATH);
    this.tools = new ACLRehabTools(this.db);
    
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

    // Set default surgery date from env if provided
    if (process.env.SURGERY_DATE) {
      console.log(`[CONFIG] Default surgery date: ${process.env.SURGERY_DATE}`);
    }
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
    console.log(`[COACH] Processing message from ${userId}`);

    // STEP 1: Safety Interceptor (BEFORE LLM)
    const safetyCheck = this.safety.checkMessage(messageText);
    
    if (safetyCheck.hasRedFlag) {
      console.log(`[SAFETY] 🚨 RED FLAG DETECTED - Sending emergency response`);
      return safetyCheck.response;
    }

    // STEP 2: Initialize user if needed
    await this.initializeUser(userId);

    // STEP 3: Send typing indicator
    await this.whatsapp.sendTyping(userId, true);

    try {
      // STEP 4: Get conversation history
      const messages = this.getConversationHistory(userId);
      
      // Add new user message
      messages.push({
        role: 'user',
        content: messageText
      });

      // STEP 5: Call LLM with tools
      const response = await this.llm.chat(
        messages,
        this.tools.getToolDefinitions()
      );

      // STEP 6: Handle tool calls
      if (response.toolCalls && response.toolCalls.length > 0) {
        console.log(`[COACH] Processing ${response.toolCalls.length} tool calls`);
        
        const toolResults = [];
        
        for (const toolCall of response.toolCalls) {
          const toolName = toolCall.function.name;
          const toolArgs = JSON.parse(toolCall.function.arguments);
          
          console.log(`[TOOL] Executing: ${toolName}`, toolArgs);
          
          const result = await this.tools.executeTool(toolName, userId, toolArgs);
          toolResults.push({
            toolCallId: toolCall.id,
            toolName,
            result
          });
        }

        // Add assistant message with tool calls to history
        messages.push({
          role: 'assistant',
          content: response.content || '',
          tool_calls: response.toolCalls
        });

        // Add tool results to history (format depends on provider)
        if (this.llm.provider === 'anthropic') {
          // Anthropic format: user role with tool_result content blocks
          const toolResultBlocks = toolResults.map(tr => ({
            type: 'tool_result',
            tool_use_id: tr.toolCallId,
            content: JSON.stringify(tr.result)
          }));
          
          messages.push({
            role: 'user',
            content: toolResultBlocks
          });
        } else {
          // OpenAI/Google format: tool role
          for (const tr of toolResults) {
            messages.push({
              role: 'tool',
              tool_call_id: tr.toolCallId,
              name: tr.toolName,
              content: JSON.stringify(tr.result)
            });
          }
        }

        // Get final response from LLM after tool execution
        const finalResponse = await this.llm.chat(messages);
        
        // Update conversation history
        messages.push({
          role: 'assistant',
          content: finalResponse.content
        });
        
        this.updateConversationHistory(userId, messages);
        
        await this.whatsapp.sendTyping(userId, false);
        return finalResponse.content;

      } else {
        // No tool calls - direct response
        messages.push({
          role: 'assistant',
          content: response.content
        });
        
        this.updateConversationHistory(userId, messages);
        
        await this.whatsapp.sendTyping(userId, false);
        return response.content;
      }

    } catch (error) {
      console.error('[COACH] Error processing message:', error);
      
      // Auto-heal for Anthropic format errors
      const errMsg = String(error?.message || '');
      if (this.llm.provider === 'anthropic' &&
          (errMsg.includes('Input should be a valid list') || errMsg.includes('Unexpected role "tool"'))) {
        console.warn(`[COACH] Resetting conversation history for ${userId} due to Anthropic format error`);
        this.conversations.set(userId, [{ role: 'system', content: this.llm.getSystemPrompt() }]);
        await this.whatsapp.sendTyping(userId, false);
        return '❌ I hit a temporary formatting issue and recovered. Please send your check-in once more.';
      }
      
      await this.whatsapp.sendTyping(userId, false);
      return '❌ I apologize, but I encountered a technical issue. Please try sending your message again.';
    }
  }

  async initializeUser(userId) {
    let userConfig = this.db.getUserConfig(userId);
    
    if (!userConfig) {
      // Create user with default surgery date from env
      const surgeryDate = process.env.SURGERY_DATE || new Date().toISOString().split('T')[0];
      
      this.db.setSurgeryDate(userId, surgeryDate);
      console.log(`[COACH] Initialized new user: ${userId} with surgery date: ${surgeryDate}`);
      
      // Initialize conversation with system prompt
      this.conversations.set(userId, [
        {
          role: 'system',
          content: this.llm.getSystemPrompt()
        }
      ]);
    } else if (!this.conversations.has(userId)) {
      // User exists but no conversation history - initialize
      this.conversations.set(userId, [
        {
          role: 'system',
          content: this.llm.getSystemPrompt()
        }
      ]);
    }
  }

  getConversationHistory(userId) {
    return this.conversations.get(userId) || [
      {
        role: 'system',
        content: this.llm.getSystemPrompt()
      }
    ];
  }

  updateConversationHistory(userId, messages) {
    // Keep last 20 messages to avoid context overflow
    const maxMessages = 20;
    
    if (messages.length > maxMessages) {
      // Always keep system message
      const systemMsg = messages[0];
      const recentMessages = messages.slice(-maxMessages + 1);
      this.conversations.set(userId, [systemMsg, ...recentMessages]);
    } else {
      this.conversations.set(userId, messages);
    }
  }

  async start() {
    console.log('🦞 ACL Rehab Coach Starting...\n');
    console.log(`LLM Provider: ${process.env.LLM_PROVIDER || 'openai'}`);
    console.log(`Model: ${process.env.LLM_MODEL || 'gpt-4o'}`);
    console.log(`Database: ${process.env.DATABASE_PATH || './data/acl_rehab.db'}\n`);
    
    await this.whatsapp.connect();
    
    console.log('\n✅ ACL Rehab Coach is running!');
    console.log('   Waiting for WhatsApp messages...\n');
  }

  async stop() {
    console.log('\n🛑 Shutting down ACL Rehab Coach...');
    await this.whatsapp.disconnect();
    this.db.close();
    console.log('✅ Shutdown complete');
    process.exit(0);
  }
}

// Start the application
const coach = new ACLRehabCoach();

// Handle graceful shutdown
process.on('SIGINT', () => coach.stop());
process.on('SIGTERM', () => coach.stop());

// Start the bot
coach.start().catch(error => {
  console.error('❌ Fatal error starting ACL Rehab Coach:', error);
  process.exit(1);
});

export default ACLRehabCoach;
