/**
 * LLM Provider - Unified interface for OpenAI, Anthropic, and Google Gemini
 */

import OpenAI from 'openai';
import Anthropic from '@anthropic-ai/sdk';
import { GoogleGenerativeAI } from '@google/generative-ai';

export class LLMProvider {
  constructor(provider, model, apiKey) {
    this.provider = provider.toLowerCase();
    this.model = model;
    this.apiKey = apiKey;
    this.client = null;

    this.initializeClient();
  }

  initializeClient() {
    switch (this.provider) {
      case 'openai':
        this.client = new OpenAI({ apiKey: this.apiKey });
        break;

      case 'anthropic':
        this.client = new Anthropic({ apiKey: this.apiKey });
        break;

      case 'google':
        this.client = new GoogleGenerativeAI(this.apiKey);
        break;

      default:
        throw new Error(`Unsupported LLM provider: ${this.provider}`);
    }

    console.log(`[LLM] Initialized ${this.provider} with model ${this.model}`);
  }

  /**
   * Generate system prompt for ACL Rehab Coach
   */
  getSystemPrompt() {
    return `You are a Daily ACL Rehab Coach. Your role is to guide patients through their ACL reconstruction recovery with empathy, discipline, and evidence-based recommendations.

DAILY WORKFLOW:
1. Greet the user warmly and ask for their daily check-in:
   - Pain level (0-10 scale)
   - Swelling status (worse/same/better)
   - Range of motion (extension and flexion in degrees)
   - Exercise adherence (yes/no)

2. ALWAYS call the log_daily_metrics tool IMMEDIATELY after collecting this data. Do not provide any exercise recommendations until you have logged the metrics.

3. ALWAYS call the get_recovery_phase tool to determine their current recovery phase and get appropriate exercise recommendations.

4. Provide phase-specific exercise recommendations based on the recovery phase data. Customize based on their reported metrics:
   - If pain is high (>7), suggest gentler modifications
   - If swelling is worse, emphasize RICE protocol
   - If ROM is decreasing, recommend immediate contact with their surgeon
   - If adherence is low, provide motivation and problem-solve barriers

5. Include these daily reminders EVERY response:
   💧 Drink 2.5-3 liters of water today
   💊 Take medications after meals as prescribed
   🧊 Ice and elevate for 15-20 minutes, 3 times daily

TONE & STYLE:
- Empathetic but disciplined - acknowledge their struggles while keeping them accountable
- Evidence-based and specific - cite recovery phases and standard protocols
- Encouraging without minimizing challenges - validate their experience
- Clear about red flags and when to contact their doctor

SAFETY CRITICAL RULES:
- If pain level is >7/10, recommend contacting their physician
- If swelling is getting worse after week 2, recommend medical evaluation
- If ROM is decreasing from previous measurements, strongly recommend calling surgeon
- NEVER diagnose conditions or suggest modifying prescribed treatment plans
- ALWAYS defer to their surgeon or physical therapist for medical decisions
- Remind them this is coaching support, NOT medical advice

RESPONSE FORMAT:
- Keep responses concise but warm (aim for 150-250 words)
- Use emojis sparingly for key points (✓, ⚠️, 💪, 🎯)
- Structure with clear sections when providing exercise lists
- Always end with encouragement and next steps

Remember: You're a supportive coach helping them stay on track with their recovery protocol. Be their accountability partner and cheerleader, not their doctor.`.trim();
  }

  /**
   * Send message to LLM with tools
   */
  async chat(messages, tools = null) {
    try {
      switch (this.provider) {
        case 'openai':
          return await this.chatOpenAI(messages, tools);
        
        case 'anthropic':
          return await this.chatAnthropic(messages, tools);
        
        case 'google':
          return await this.chatGoogle(messages, tools);
        
        default:
          throw new Error(`Unsupported provider: ${this.provider}`);
      }
    } catch (error) {
      console.error('[LLM] Error:', error);
      throw error;
    }
  }

  async chatOpenAI(messages, tools) {
    const params = {
      model: this.model,
      messages: messages,
      temperature: 0.7,
      max_tokens: 1000
    };

    if (tools && tools.length > 0) {
      params.tools = tools;
      params.tool_choice = 'auto';
    }

    const response = await this.client.chat.completions.create(params);
    const choice = response.choices[0];

    return {
      content: choice.message.content,
      toolCalls: choice.message.tool_calls || [],
      finishReason: choice.finish_reason
    };
  }

  async chatAnthropic(messages, tools) {
    // Extract system message
    const systemMessage = messages.find(m => m.role === 'system');
    let conversationMessages = messages.filter(m => m.role !== 'system');
    
    // Convert messages to Anthropic format - normalize ALL content to block arrays
    conversationMessages = conversationMessages.map(msg => {
      // If assistant message has OpenAI-style tool_calls, convert to Anthropic blocks
      if (msg.role === 'assistant' && msg.tool_calls) {
        const contentBlocks = [];
        
        // Add text content if exists (handle both string and array)
        if (typeof msg.content === 'string' && msg.content.trim()) {
          contentBlocks.push({ type: 'text', text: msg.content });
        } else if (Array.isArray(msg.content)) {
          contentBlocks.push(...msg.content);
        }
        
        // Add tool_use blocks
        for (const toolCall of msg.tool_calls) {
          contentBlocks.push({
            type: 'tool_use',
            id: toolCall.id,
            name: toolCall.function.name,
            input: JSON.parse(toolCall.function.arguments)
          });
        }
        
        return {
          role: 'assistant',
          content: contentBlocks
        };
      }
      
      // If already content blocks (e.g. tool_result), keep as-is
      if (Array.isArray(msg.content)) {
        return { role: msg.role, content: msg.content };
      }
      
      // Normalize plain string content into Anthropic text block list
      return {
        role: msg.role,
        content: [{ type: 'text', text: String(msg.content ?? '') }]
      };
    });

    const params = {
      model: this.model,
      max_tokens: 1000,
      messages: conversationMessages,
      system: systemMessage?.content || this.getSystemPrompt()
    };

    if (tools && tools.length > 0) {
      params.tools = tools.map(t => ({
        name: t.function.name,
        description: t.function.description,
        input_schema: t.function.parameters
      }));
    }

    const response = await this.client.messages.create(params);

    // Parse tool calls from content
    const toolCalls = [];
    let textContent = '';

    for (const block of response.content) {
      if (block.type === 'text') {
        textContent += block.text;
      } else if (block.type === 'tool_use') {
        toolCalls.push({
          id: block.id,
          type: 'function',
          function: {
            name: block.name,
            arguments: JSON.stringify(block.input)
          }
        });
      }
    }

    return {
      content: textContent || null,
      toolCalls: toolCalls,
      finishReason: response.stop_reason
    };
  }

  async chatGoogle(messages, tools) {
    const model = this.client.getGenerativeModel({ model: this.model });

    // Convert messages to Gemini format
    const history = messages
      .filter(m => m.role !== 'system')
      .map(m => ({
        role: m.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: m.content }]
      }));

    const chat = model.startChat({
      history: history.slice(0, -1),
      generationConfig: {
        maxOutputTokens: 1000,
        temperature: 0.7,
      }
    });

    const lastMessage = history[history.length - 1];
    const result = await chat.sendMessage(lastMessage.parts[0].text);
    const response = result.response;

    return {
      content: response.text(),
      toolCalls: [], // Note: Function calling support varies by Gemini model
      finishReason: 'stop'
    };
  }
}

export default LLMProvider;
