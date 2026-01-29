
import React, { useState, useEffect, useRef } from 'react';
import { Settings, Send, Trash2, Smartphone, Cpu, RefreshCcw, Activity, ShieldAlert } from 'lucide-react';
import { Message, ChatSettings, Role } from './types';
import { ChatMessage } from './components/ChatMessage';
import { SettingsModal } from './components/SettingsModal';
import { streamChat } from './services/chatService';

const DEFAULT_SETTINGS: ChatSettings = {
  serverUrl: 'http://100.107.136.88:6969',
  apiKey: 'home-link-secret',
  model: 'default',
  temperature: 0.7,
  maxTokens: 2048,
  systemPrompt: 'You are a helpful, concise AI assistant running locally on an Alienware PC.',
};

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const [settings, setSettings] = useState<ChatSettings>(() => {
    const saved = localStorage.getItem('homelink_settings');
    if (saved) {
      const parsed = JSON.parse(saved);
      return { ...DEFAULT_SETTINGS, ...parsed };
    }
    return DEFAULT_SETTINGS;
  });

  const isHttps = window.location.protocol === 'https:';
  const isTargetHttp = settings.serverUrl.startsWith('http:');

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
    <div className="flex flex-col h-screen max-h-screen bg-slate-50 overflow-hidden">
      <header className="flex items-center justify-between px-4 h-16 bg-white border-b border-slate-200 shrink-0 sticky top-0 z-10 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="bg-blue-600 p-2 rounded-xl shadow-blue-200 shadow-lg">
            <Cpu className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-slate-800 leading-tight">HomeLink</h1>
              <div className={`w-2 h-2 rounded-full ${
                isConnected === null ? 'bg-slate-300 animate-pulse' : 
                isConnected ? 'bg-green-500 shadow-green-200 shadow-lg' : 'bg-red-500 shadow-red-200 shadow-lg'
              }`} />
            </div>
            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">Alienware Proxy</p>
          </div>
        </div>
        
        <div className="flex items-center gap-1">
          <button 
            onClick={() => setMessages([])}
            className="p-2 text-slate-400 hover:text-red-500 transition-colors"
          >
            <Trash2 className="w-5 h-5" />
          </button>
          <button 
            onClick={() => setIsSettingsOpen(true)}
            className="p-2 text-slate-600 hover:bg-slate-100 rounded-full transition-colors relative"
          >
            <Settings className="w-6 h-6" />
            {isConnected === false && <div className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white" />}
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-4 space-y-6 pb-32 scroll-smooth">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-400 text-center px-8 animate-in fade-in zoom-in duration-700">
            <div className="relative mb-6">
              <Smartphone className="w-16 h-16 opacity-10" />
              {isConnected === false && <ShieldAlert className="absolute inset-0 w-8 h-8 m-auto text-red-500 animate-bounce" />}
            </div>
            <p className="text-xl font-bold text-slate-700">
              {isConnected === false ? 'Connection Required' : 'Secure HomeLink Active'}
            </p>
            <p className="text-sm max-w-xs mt-2 leading-relaxed">
              {isConnected === false 
                ? "Your browser is blocking the connection. Ensure you allowed Insecure Content for 100.107.136.88."
                : "Your messages are being forwarded securely to your local LLM."}
            </p>
          </div>
        ) : (
          messages.map(msg => (
            <ChatMessage key={msg.id} message={msg} />
          ))
        )}
        <div ref={messagesEndRef} />
      </main>

      <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-white via-white to-transparent">
        <div className="max-w-4xl mx-auto flex items-end gap-2 bg-white rounded-2xl p-2 shadow-2xl border border-slate-200">
          <textarea
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSend())}
            placeholder="Type a message..."
            className="flex-1 max-h-32 resize-none bg-transparent border-none focus:ring-0 p-3 text-slate-800 text-sm"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading || isConnected === false}
            className={`p-3.5 rounded-xl transition-all ${
              !input.trim() || isLoading || isConnected === false
                ? 'bg-slate-100 text-slate-300' 
                : 'bg-blue-600 text-white shadow-md active:scale-90'
            }`}
          >
            {isLoading ? <RefreshCcw className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
          </button>
        </div>
      </div>

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
