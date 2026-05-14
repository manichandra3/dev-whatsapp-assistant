/**
 * WhatsApp Bot - Baileys Integration
 * 
 * Handles WhatsApp connection, message handling, and QR code authentication
 */

import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
  fetchLatestBaileysVersion,
  downloadContentFromMessage,
  getContentType
} from '@whiskeysockets/baileys';
import pino from 'pino';
import qrcode from 'qrcode-terminal';

export class WhatsAppBot {
  constructor(sessionPath, onMessage) {
    this.sessionPath = sessionPath;
    this.onMessage = onMessage;
    this.sock = null;
    this.qr = null;
    
    // Rate limiting (Token Bucket per account)
    this.rateLimitPerMin = parseInt(process.env.WHATSAPP_SEND_RATE_LIMIT_PER_MIN || '10', 10);
    this.tokens = this.rateLimitPerMin;
    this.lastRefill = Date.now();
    this.sendQueue = [];
    this.isProcessingQueue = false;

    this.logger = pino({ 
      level: process.env.LOG_LEVEL || 'warn',  // Reduce Baileys internal noise
      transport: {
        target: 'pino-pretty',
        options: {
          colorize: true,
          ignore: 'hostname'
        }
      }
    });
  }

  async connect() {
    const { state, saveCreds } = await useMultiFileAuthState(this.sessionPath);
    const { version } = await fetchLatestBaileysVersion();

    this.sock = makeWASocket({
      version,
      logger: this.logger,
      printQRInTerminal: false, // We'll handle QR display ourselves
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, this.logger)
      },
      getMessage: async (key) => {
        return { conversation: 'Message not found' };
      }
    });

    // Save credentials on update
    this.sock.ev.on('creds.update', saveCreds);

    // Handle connection updates
    this.sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      // Display QR code
      if (qr) {
        console.log('\n📱 Scan this QR code with WhatsApp:\n');
        qrcode.generate(qr, { small: true });
        console.log('\nOpen WhatsApp > Linked Devices > Link a Device\n');
      }

      // Connection status
      if (connection === 'close') {
        const shouldReconnect = 
          lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
        
        console.log('[WhatsApp] Connection closed. Reconnecting:', shouldReconnect);
        
        if (shouldReconnect) {
          setTimeout(() => this.connect(), 3000);
        } else {
          console.log('[WhatsApp] Logged out. Please restart and scan QR code again.');
          process.exit(0);
        }
      } else if (connection === 'open') {
        console.log('✅ [WhatsApp] Connected successfully!');
      }
    });

    // Handle incoming messages
    this.sock.ev.on('messages.upsert', async ({ messages, type }) => {
      if (type !== 'notify') return;

      for (const msg of messages) {
        await this.handleMessage(msg);
      }
    });
  }

  async handleMessage(msg) {
    // Ignore messages from self or status updates
    if (msg.key.fromMe || msg.key.remoteJid === 'status@broadcast') {
      return;
    }

    // Ignore group chats (only handle DMs)
    if (msg.key.remoteJid?.endsWith('@g.us')) {
      return;
    }

    // Ignore reactions, edits, and other non-text message types
    if (msg.message?.reactionMessage || 
        msg.message?.protocolMessage ||
        msg.message?.editedMessage) {
      return;
    }

    const imagePayload = await this.extractImageMessage(msg);

    const messageText = msg.message?.conversation || 
                       msg.message?.extendedTextMessage?.text ||
                       imagePayload?.caption ||
                       '';

    if (!messageText && !imagePayload) return;

    const sender = msg.key.remoteJid;
    
    console.log(`\n📩 Message from ${sender}:`);
    if (messageText) {
      console.log(`   "${messageText}"`);
    }
    if (imagePayload) {
      console.log(`   [image] ${imagePayload.fileName || 'upload'} (${imagePayload.mimeType || 'unknown'})`);
    }
    console.log('');

    try {
      // Call the message handler (from main app)
      if (this.onMessage) {
        // Pass contextInfo from incoming message for reply matching
        const contextInfo = msg.message?.contextInfo || null;
        const response = await this.onMessage(sender, messageText, imagePayload, contextInfo);
        
        if (response) {
          // Forward contextInfo to sendMessage so the bridge can include it
          await this.sendMessage(sender, response, contextInfo);
        }
      }
    } catch (error) {
      console.error('[WhatsApp] Error handling message:', error);
      await this.sendMessage(
        sender, 
        '❌ Sorry, I encountered an error processing your message. Please try again.'
      );
    }
  }

  async extractImageMessage(msg) {
    try {
      const contentType = getContentType(msg.message);
      let imageMessage = null;

      if (contentType === 'imageMessage') {
        imageMessage = msg.message?.imageMessage;
      } else if (contentType === 'viewOnceMessageV2') {
        imageMessage = msg.message?.viewOnceMessageV2?.message?.imageMessage;
      } else if (contentType === 'viewOnceMessage') {
        imageMessage = msg.message?.viewOnceMessage?.message?.imageMessage;
      }

      if (!imageMessage) return null;

      const stream = await downloadContentFromMessage(imageMessage, 'image');
      const buffer = await this.streamToBuffer(stream);
      const mimeType = imageMessage.mimetype || 'image/jpeg';
      const fileName = imageMessage.fileName || `image-${Date.now()}.jpg`;

      return {
        buffer,
        mimeType,
        fileName,
        size: imageMessage.fileLength ? Number(imageMessage.fileLength) : buffer.length,
        caption: imageMessage.caption || ''
      };
    } catch (error) {
      console.error('[WhatsApp] Error extracting image:', error);
      return null;
    }
  }

  async streamToBuffer(stream) {
    const chunks = [];
    for await (const chunk of stream) {
      chunks.push(chunk);
    }
    return Buffer.concat(chunks);
  }

  async sendMessage(jid, content, context = null) {
    if (!this.sock) {
      throw new Error('WhatsApp socket not connected');
    }

    return new Promise((resolve, reject) => {
      this.sendQueue.push({ jid, content, context, resolve, reject });
      this.processQueue();
    });
  }

  async processQueue() {
    if (this.isProcessingQueue) return;
    this.isProcessingQueue = true;

    while (this.sendQueue.length > 0) {
      // Refill tokens
      const now = Date.now();
      const elapsedMinutes = (now - this.lastRefill) / 60000;
      if (elapsedMinutes >= 1) {
        this.tokens = this.rateLimitPerMin;
        this.lastRefill = now;
      }

      if (this.tokens <= 0) {
        // Wait until next refill window
        const waitTime = 60000 - ((now - this.lastRefill) % 60000);
        await new Promise(resolve => setTimeout(resolve, waitTime));
        continue;
      }

      const { jid, content, context, resolve, reject } = this.sendQueue.shift();
      this.tokens--;

      try {
        let messagePayload;
        
        // Handle structured vs string content
        if (typeof content === 'string') {
          messagePayload = { text: content };
        } else {
          messagePayload = this.mapPayload(content.text, content.whatsapp_payload);
        }

        const res = await this.sock.sendMessage(jid, messagePayload);
        // Baileys returns a message ID/key - attempt to extract stanzaId
        const stanzaId = res?.key?.id || res?.key?.remoteJid || null;
        console.log(`✅ Sent message to ${jid} (stanzaId=${stanzaId})`);
        // Return stanzaId and include context so bridge can persist it
        resolve({ success: true, stanzaId, context });
      } catch (error) {
        console.error('[WhatsApp] Error sending message:', error);
        reject(error);
      }
    }

    this.isProcessingQueue = false;
  }

  validateWhatsappPayload(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const validTypes = ['text', 'buttons', 'list', 'media', 'interactive'];
    if (!validTypes.includes(payload.type)) return null;
    return payload;
  }

  mapPayload(text, payload) {
    if (!payload) return { text: text || '' };
    
    const validPayload = this.validateWhatsappPayload(payload);
    if (!validPayload) return { text: text || '' };

    if (validPayload.type === 'buttons') {
      return {
        text: validPayload.text || text,
        footer: validPayload.footer,
        buttons: validPayload.buttons,
        headerType: 1
      };
    } else if (validPayload.type === 'list') {
      return {
        text: validPayload.text || text,
        title: validPayload.title,
        buttonText: validPayload.buttonText,
        sections: validPayload.sections
      };
    } else if (validPayload.type === 'media') {
      return {
        [validPayload.mediaType || 'image']: { url: validPayload.url },
        caption: validPayload.caption || text
      };
    } else if (validPayload.type === 'interactive') {
      return validPayload.message; // Passthrough for arbitrary interactive messages
    }
    
    return { text: validPayload.text || text || '' };
  }

  async sendTyping(jid, isTyping = true) {
    if (!this.sock) return;

    try {
      await this.sock.sendPresenceUpdate(
        isTyping ? 'composing' : 'paused', 
        jid
      );
    } catch (error) {
      console.error('[WhatsApp] Error sending typing indicator:', error);
    }
  }

  async disconnect() {
    if (this.sock) {
      await this.sock.logout();
      console.log('[WhatsApp] Disconnected');
    }
  }

  isConnected() {
    return this.sock?.user != null;
  }

  getUser() {
    return this.sock?.user;
  }
}

export default WhatsAppBot;
