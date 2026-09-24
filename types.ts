
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
  cameraUrls: string[];
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

export interface GuardCameraInfo {
  id: number;
  camera_ok: boolean;
  last_motion: number | null;
  type?: string;
  name?: string;
  /** this camera has its own microphone mapped (older guards omit these) */
  has_audio?: boolean;
  audio_device?: string | null;
}

export interface GuardStatus {
  status: string;
  service: string;
  node_id?: string;
  hostname?: string;
  camera_ok: boolean;
  cameras: GuardCameraInfo[];
  armed: boolean;
  uptime_seconds: number;
  last_motion: number | null;
  event_count: number;
  camera_roll?: string;
  camera_roll_ready?: boolean;
}

export interface GuardEvent {
  name: string;
  time: string;
  cam: number;
  type?: 'motion' | 'capture';
  node?: string | null;
}
