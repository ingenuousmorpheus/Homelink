
import React, { useState, useEffect, useRef } from 'react';
import { Settings, Send, Trash2, Cpu, RefreshCcw, ShieldAlert, MessageSquare, Video } from 'lucide-react';
import { Message, ChatSettings, Role } from './types';
import { ChatMessage } from './components/ChatMessage';
import { SettingsModal } from './components/SettingsModal';
import { CameraView } from './components/CameraView';
import { streamChat } from './services/chatService';

const DEFAULT_SETTINGS: ChatSettings = {
  serverUrl: 'http://100.107.136.88:6969',
  apiKey: 'home-link-secret',
  cameraUrls: [
    'http://100.110.73.8:7171',    // RedKryptonite
    'http://100.115.8.121:7171',   // LenovoMonitor
    'http://100.107.136.88:7171',  // Alienware
  ],
  model: 'default',
  temperature: 0.7,
  maxTokens: 2048,
  systemPrompt: 'You are a helpful, concise AI assistant running locally on an Alienware PC.',
};

type AppView = 'chat' | 'guard';

export default function App() {
  const [view, setView] = useState<AppView>('chat');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const [settings, setSettings] = useState<ChatSettings>(() => {
    try {
      const saved = localStorage.getItem('homelink_settings');
      if (!saved) return DEFAULT_SETTINGS;
      const parsed = JSON.parse(saved);
      // migrate old single-url fields, then merge in any new default nodes
      // so freshly added cameras appear without touching settings
      const legacy = [parsed.cameraUrl, parsed.cameraUrl2].filter(Boolean);
      const savedUrls: string[] = Array.isArray(parsed.cameraUrls) ? parsed.cameraUrls : legacy;
      const cameraUrls = Array.from(new Set([...DEFAULT_SETTINGS.cameraUrls, ...savedUrls]));
      delete parsed.cameraUrl;
      delete parsed.cameraUrl2;
      return { ...DEFAULT_SETTINGS, ...parsed, cameraUrls };
    } catch {
      return DEFAULT_SETTINGS;
    }
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const url = settings.serverUrl.replace(/\/$/, '');
        const controller = new AbortController();
        const tid = setTimeout(() => controller.abort(), 3000);
        const resp = await fetch(`${url}/`, {
          method: 'GET',
          headers: { 'X-API-Key': settings.apiKey },
          signal: controller.signal
        });
        clearTimeout(tid);
        setIsConnected(resp.ok);
      } catch {
        setIsConnected(false);
      }
    };

    checkConnection();
    const interval = setInterval(checkConnection, 10000);
    return () => clearInterval(interval);
  }, [settings.serverUrl, settings.apiKey]);

  useEffect(() => {
    localStorage.setItem('homelink_settings', JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: Date.now(),
    };

    const assistantId = (Date.now() + 1).toString();
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: Date.now() + 1,
    };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const history = [
        { role: 'system' as Role, content: settings.systemPrompt },
        ...messages.map(m => ({ role: m.role, content: m.content })),
        { role: 'user' as Role, content: userMsg.content }
      ];

      await streamChat(
        settings.serverUrl,
        settings.apiKey,
        {
          model: settings.model,
          messages: history,
          temperature: settings.temperature,
          max_tokens: settings.maxTokens,
          stream: true
        },
        (chunk) => {
          setMessages(prev => prev.map(m =>
            m.id === assistantId ? { ...m, content: m.content + chunk } : m
          ));
        }
      );
    } catch (error: any) {
      setMessages(prev => prev.map(m =>
        m.id === assistantId ? { ...m, content: m.content + `\n\n[Error: ${error.message}]` } : m
      ));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen max-h-screen overflow-hidden">
      <header className="flex items-center justify-between px-4 h-14 shrink-0 sticky top-0 z-10 border-b border-[var(--border)] bg-[linear-gradient(180deg,rgba(20,13,24,.85),rgba(12,8,16,.5))] backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="border border-[var(--border-bright)] p-1.5 bg-[rgba(255,184,90,.06)]">
            <Cpu className="w-4 h-4 text-[var(--gold)]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-cyber font-black text-sm tracking-[0.3em] text-[var(--gold)] glow-gold leading-tight">
                HOMELINK
              </h1>
              <div className={`w-2 h-2 rounded-full ${
                isConnected === null ? 'bg-[var(--dim)] animate-pulse' :
                isConnected ? 'bg-[var(--green)] shadow-[0_0_10px_var(--green)]' : 'bg-[var(--red)] shadow-[0_0_10px_var(--red)]'
              }`} />
            </div>
            <p className="font-term text-[9px] text-[var(--dim)] tracking-[0.3em] uppercase">
              {view === 'chat' ? 'Neural Uplink // Alienware' : 'Sentinel // RedKryptonite'}
            </p>
          </div>
        </div>

        <div className="flex items-center border border-[var(--border)] bg-black/30">
          <button
            onClick={() => setView('chat')}
            className={`px-3 py-2 flex items-center gap-1.5 font-cyber text-[9px] tracking-[0.2em] transition-all ${
              view === 'chat'
                ? 'text-[var(--cyan)] glow-cyan bg-[rgba(92,200,255,.08)] border-b-2 border-[var(--cyan)]'
                : 'text-[var(--dim)] border-b-2 border-transparent'
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">NEURAL</span>
          </button>
          <button
            onClick={() => setView('guard')}
            className={`px-3 py-2 flex items-center gap-1.5 font-cyber text-[9px] tracking-[0.2em] transition-all ${
              view === 'guard'
                ? 'text-[var(--gold)] glow-gold bg-[rgba(255,184,90,.08)] border-b-2 border-[var(--gold)]'
                : 'text-[var(--dim)] border-b-2 border-transparent'
            }`}
          >
            <Video className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">SENTINEL</span>
          </button>
        </div>

        <div className="flex items-center gap-1">
          {view === 'chat' && (
            <button
              onClick={() => setMessages([])}
              className="p-2 text-[var(--dim)] hover:text-[var(--red)] transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => setIsSettingsOpen(true)}
            className="p-2 text-[var(--dim)] hover:text-[var(--gold)] transition-colors relative"
          >
            <Settings className="w-5 h-5" />
            {isConnected === false && <div className="absolute top-1 right-1 w-2 h-2 bg-[var(--red)] rounded-full shadow-[0_0_6px_var(--red)]" />}
          </button>
        </div>
      </header>

      <main className={`flex-1 overflow-y-auto p-4 space-y-6 scroll-smooth ${view === 'chat' ? 'pb-32' : 'pb-6'}`}>
        {view === 'guard' ? (
          <CameraView settings={settings} setSettings={setSettings} />
        ) : messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center px-8">
            <div className="relative mb-6 border border-[var(--border)] p-6">
              <Cpu className="w-12 h-12 text-[var(--gold)] opacity-20" />
              {isConnected === false && <ShieldAlert className="absolute inset-0 w-8 h-8 m-auto text-[var(--red)] glow-red" />}
            </div>
            <p className="font-cyber text-sm font-bold tracking-[0.25em] text-[var(--gold)] glow-gold">
              {isConnected === false ? 'UPLINK SEVERED' : 'NEURAL LINK ACTIVE'}
            </p>
            <p className="font-term text-[11px] text-[var(--dim)] max-w-xs mt-3 leading-relaxed tracking-wider">
              {isConnected === false
                ? '// BROWSER BLOCKING CONNECTION - ALLOW INSECURE CONTENT FOR 100.107.136.88 //'
                : '// MESSAGES ROUTE TO THE LOCAL LLM ON YOUR ALIENWARE //'}
            </p>
          </div>
        ) : (
          messages.map(msg => (
            <ChatMessage key={msg.id} message={msg} />
          ))
        )}
        <div ref={messagesEndRef} />
      </main>

      {view === 'chat' && (
      <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-[var(--bg)] via-[var(--bg)] to-transparent">
        <div className="max-w-4xl mx-auto flex items-end gap-2 bg-[var(--panel-solid)] border border-[var(--border)] p-2">
          <textarea
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSend())}
            placeholder="> transmit message..."
            className="flex-1 max-h-32 resize-none bg-transparent border-none focus:ring-0 focus:outline-none p-3 text-[var(--text)] font-term text-sm"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading || isConnected === false}
            className={`p-3.5 transition-all border ${
              !input.trim() || isLoading || isConnected === false
                ? 'border-[var(--border)] text-[var(--dim)] opacity-50'
                : 'border-[var(--border-bright)] bg-[rgba(255,184,90,.1)] text-[var(--gold)] shadow-[0_0_16px_rgba(255,184,90,.25)] active:scale-90'
            }`}
          >
            {isLoading ? <RefreshCcw className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
          </button>
        </div>
      </div>
      )}

      {isSettingsOpen && (
        <SettingsModal
          settings={settings}
          setSettings={setSettings}
          onClose={() => setIsSettingsOpen(false)}
        />
      )}
    </div>
  );
}
