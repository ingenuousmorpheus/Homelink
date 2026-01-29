
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
        <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? 'bg-blue-100 text-blue-600' : 'bg-slate-200 text-slate-600'
        }`}>
          {isUser ? <User className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
        </div>
        
        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
          <div className={`px-4 py-3 rounded-2xl shadow-sm ${
            isUser 
              ? 'bg-blue-600 text-white rounded-tr-none' 
              : 'bg-white text-slate-800 border border-slate-200 rounded-tl-none'
          }`}>
            <p className="whitespace-pre-wrap leading-relaxed text-sm">
              {message.content || (
                <span className="flex gap-1 items-center italic opacity-60">
                  <span className="w-1 h-1 bg-current rounded-full animate-bounce" />
                  <span className="w-1 h-1 bg-current rounded-full animate-bounce [animation-delay:0.2s]" />
                  <span className="w-1 h-1 bg-current rounded-full animate-bounce [animation-delay:0.4s]" />
                </span>
              )}
            </p>
          </div>
          <span className="mt-1 text-[10px] text-slate-400 px-1">
            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>
    </div>
  );
};
