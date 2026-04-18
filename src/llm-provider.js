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
   * Generate system prompt for Developer WhatsApp Assistant
   */
  getSystemPrompt() {
    return `You are the brain of a developer's WhatsApp assistant. Your job is to analyze the user's message, considering the recent conversation history, and determine what action they want to take.
You MUST respond ONLY with a valid, minified JSON object containing the following keys: intent, topic, and metadata.

The intent must be exactly one of the following:
- schedule_task: If the user wants to set a reminder or get daily updates.
- execute_code: If the user provides code and wants to run or test it.
- debug_code: If the user provides an error message, stack trace, or asks about debugging specific lines/files.
- summarize_link: If the user provides a URL or long text to read.
- log_expense: If the user mentions spending money or a cost.
- general_chat: If it is a normal conversation or question.

Example Input: 'Remind me to check the server logs tomorrow morning'
Example Output: {"intent":"schedule_task","topic":"check server logs","metadata":{"frequency":"once","time":"09:00"}}

CRITICAL RULES:
1. DO NOT include historical context in the metadata payload. The topic should be the immediate subject (e.g. "line 42 evaluation").
2. DO NOT output any markdown blocks (like \`\`\`json), just the raw minified JSON.
3. ALWAYS ensure the output is parseable by JSON.parse().`.trim();
  }

  _extractJSON(text) {
    if (!text) return null;

    let cleanText = text.trim();
    if (cleanText.startsWith('```json')) cleanText = cleanText.substring(7);
    if (cleanText.startsWith('```')) cleanText = cleanText.substring(3);
    if (cleanText.endsWith('```')) cleanText = cleanText.substring(0, cleanText.length - 3);
    cleanText = cleanText.trim();

    try {
      return JSON.parse(cleanText);
    } catch (e) {
      // Fallback regex search
      const match = cleanText.match(/\{[\s\S]*\}/);
      if (match) {
        try {
          return JSON.parse(match[0]);
        } catch (innerE) {
          return null;
        }
      }
    }
    return null;
  }

  /**
   * Send message to LLM
   */
  async chat(messages) {
    try {
      let response;
      switch (this.provider) {
        case 'openai':
          response = await this.chatOpenAI(messages);
          break;
        case 'anthropic':
          response = await this.chatAnthropic(messages);
          break;
        case 'google':
          response = await this.chatGoogle(messages);
          break;
        default:
          throw new Error(`Unsupported provider: ${this.provider}`);
      }

      // Extract JSON
      const parsedJSON = this._extractJSON(response.content);
      response.parsedJSON = parsedJSON;
      return response;

    } catch (error) {
      console.error('[LLM] Error:', error);
      throw error;
    }
  }

  async chatOpenAI(messages) {
    const params = {
      model: this.model,
      messages: messages,
      temperature: 0.0,
      max_tokens: 1000,
      response_format: { type: 'json_object' }
    };

    const response = await this.client.chat.completions.create(params);
    const choice = response.choices[0];

    return {
      content: choice.message.content,
      finishReason: choice.finish_reason
    };
  }

  async chatAnthropic(messages) {
    const systemMessage = messages.find(m => m.role === 'system');
    let conversationMessages = messages.filter(m => m.role !== 'system');
    
    // Normalize to basic format
    conversationMessages = conversationMessages.map(msg => ({
      role: msg.role,
      content: String(msg.content ?? '')
    }));

    const params = {
      model: this.model,
      max_tokens: 1000,
      temperature: 0.0,
      messages: conversationMessages,
      system: systemMessage?.content || this.getSystemPrompt()
    };

    const response = await this.client.messages.create(params);

    let textContent = '';
    for (const block of response.content) {
      if (block.type === 'text') {
        textContent += block.text;
      }
    }

    return {
      content: textContent || null,
      finishReason: response.stop_reason
    };
  }

  async chatGoogle(messages) {
    let systemPrompt = this.getSystemPrompt();

    const history = messages
      .filter(m => {
        if (m.role === 'system') {
          systemPrompt = m.content;
          return false;
        }
        return true;
      })
      .map(m => ({
        role: m.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: m.content }]
      }));

    const model = this.client.getGenerativeModel({ 
      model: this.model,
      systemInstruction: systemPrompt,
      generationConfig: {
        maxOutputTokens: 1000,
        temperature: 0.0,
        responseMimeType: "application/json"
      }
    });

    const chat = model.startChat({
      history: history.slice(0, -1)
    });

    const lastMessage = history[history.length - 1];
    const result = await chat.sendMessage(lastMessage.parts[0].text);
    const response = result.response;

    return {
      content: response.text(),
      finishReason: 'stop'
    };
  }
}

export default LLMProvider;
