/**
 * WhatsApp Bot - Baileys Integration
 * 
 * Handles WhatsApp connection, message handling, and QR code authentication
 */

import makeWASocket, { 
  DisconnectReason, 
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
  fetchLatestBaileysVersion
} from '@whiskeysockets/baileys';
import pino from 'pino';
import qrcode from 'qrcode-terminal';

export class WhatsAppBot {
  constructor(sessionPath, onMessage) {
    this.sessionPath = sessionPath;
    this.onMessage = onMessage;
    this.sock = null;
    this.qr = null;
    
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

    const messageText = msg.message?.conversation || 
                       msg.message?.extendedTextMessage?.text ||
                       '';

    if (!messageText) return;

    const sender = msg.key.remoteJid;
    
    console.log(`\n📩 Message from ${sender}:`);
    console.log(`   "${messageText}"\n`);

    try {
      // Call the message handler (from main app)
      if (this.onMessage) {
        const response = await this.onMessage(sender, messageText);
        
        if (response) {
          await this.sendMessage(sender, response);
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

  async sendMessage(jid, text) {
    if (!this.sock) {
      throw new Error('WhatsApp socket not connected');
    }

    try {
      await this.sock.sendMessage(jid, { text });
      console.log(`✅ Sent message to ${jid}`);
    } catch (error) {
      console.error('[WhatsApp] Error sending message:', error);
      throw error;
    }
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
