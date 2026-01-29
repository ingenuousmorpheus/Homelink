
export type Role = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: number;
}

export interface ChatSettings {
  serverUrl: string;
  apiKey: string;
  model: string;
  temperature: number;
  maxTokens: number;
  systemPrompt: string;
}

export interface LMStudioModel {
  id: string;
  object: string;
  owned_by: string;
}
