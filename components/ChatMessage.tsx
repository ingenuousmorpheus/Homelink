
import React from 'react';
import { Message } from '../types';
import { User, Bot } from 'lucide-react';

interface ChatMessageProps {
  message: Message;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const isUser = message.role === 'user';

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex gap-3 max-w-[90%] sm:max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <div className={`shrink-0 w-8 h-8 border flex items-center justify-center ${
          isUser
            ? 'border-[var(--border-bright)] bg-[rgba(255,184,90,.08)] text-[var(--gold)]'
            : 'border-[rgba(92,200,255,.35)] bg-[rgba(92,200,255,.06)] text-[var(--cyan)]'
        }`}>
          {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
        </div>

        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
          <div className={`px-4 py-3 border backdrop-blur-sm ${
            isUser
              ? 'border-[var(--border-bright)] bg-[rgba(255,184,90,.07)] text-[var(--text)]'
              : 'border-[rgba(92,200,255,.25)] bg-[rgba(92,200,255,.05)] text-[var(--text)]'
          }`}>
            <p className="whitespace-pre-wrap leading-relaxed text-sm">
              {message.content || (
                <span className="flex gap-1 items-center opacity-60">
                  <span className="w-1 h-1 bg-[var(--cyan)] rounded-full animate-bounce" />
                  <span className="w-1 h-1 bg-[var(--cyan)] rounded-full animate-bounce [animation-delay:0.2s]" />
                  <span className="w-1 h-1 bg-[var(--cyan)] rounded-full animate-bounce [animation-delay:0.4s]" />
                </span>
              )}
            </p>
          </div>
          <span className={`mt-1 font-term text-[9px] tracking-wider px-1 ${isUser ? 'text-[var(--gold)] opacity-50' : 'text-[var(--cyan)] opacity-50'}`}>
            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>
    </div>
  );
};
