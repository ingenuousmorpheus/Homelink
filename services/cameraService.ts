
import { GuardStatus, GuardEvent } from '../types';

const cleanUrl = (url: string) => url.trim().replace(/\/$/, '');

// <img> tags cannot send headers, so the stream/snapshot/event URLs
// carry the shared secret as a ?key= query param instead.
export const guardMediaUrl = (
  baseUrl: string,
  path: string,
  apiKey: string,
  opts: { cam?: number; cacheBust?: number; save?: boolean } = {}
) => {
  const params = new URLSearchParams({ key: apiKey });
  if (opts.cam !== undefined) params.set('cam', String(opts.cam));
  if (opts.cacheBust !== undefined) params.set('t', String(opts.cacheBust));
  if (opts.save !== undefined) params.set('save', opts.save ? '1' : '0');
  return `${cleanUrl(baseUrl)}${path}?${params.toString()}`;
};

const guardFetch = async (
  baseUrl: string,
  path: string,
  apiKey: string,
  init?: RequestInit
): Promise<Response> => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(`${cleanUrl(baseUrl)}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey,
        ...(init?.headers || {}),
      },
      mode: 'cors',
      signal: controller.signal,
    });
    if (!response.ok) {
      if (response.status === 403) throw new Error('SECRET KEY MISMATCH // check settings');
      throw new Error(`GUARD RESPONDED ${response.status}`);
    }
    return response;
  } catch (error: any) {
    if (error.name === 'AbortError') {
      throw new Error('SIGNAL TIMEOUT // is the guard running on this node?');
    }
    if (error.message === 'Failed to fetch') {
      throw new Error(
        'LINK SEVERED // check camera_server.py on this guard node ' +
        'and allow Insecure Content for its IP in this browser.'
      );
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
};

export const fetchGuardStatus = async (baseUrl: string, apiKey: string): Promise<GuardStatus> => {
  const resp = await guardFetch(baseUrl, '/', apiKey);
  const data = await resp.json();
  // tolerate the old single-camera server until the laptop is updated
  if (!data.cameras) {
    data.cameras = [{ id: 0, camera_ok: !!data.camera_ok, last_motion: data.last_motion ?? null }];
  }
  return data;
};

export const fetchGuardEvents = async (baseUrl: string, apiKey: string): Promise<GuardEvent[]> => {
  const resp = await guardFetch(baseUrl, '/events', apiKey);
  const data = await resp.json();
  return (data.events || []).map((e: any) => ({ cam: 0, ...e }));
};

export interface DiscoveredNode {
  url: string;
  cameras: number;
  node_id?: string;
  hostname?: string;
}

export interface DiscoveredIpCamera {
  ip: string;
  xaddr: string | null;
}

export interface DiscoveryResult {
  nodes: DiscoveredNode[];
  ipCameras: DiscoveredIpCamera[];
}

/** Ask each known guard node to scan the network until one answers.
 * Finds every guard node plus standalone ONVIF IP cameras. */
export const discoverNodes = async (
  baseUrls: string[],
  apiKey: string
): Promise<DiscoveryResult> => {
  const bases = Array.from(new Set(baseUrls.map(b => cleanUrl(b || '')).filter(Boolean)));
  if (bases.length === 0) throw new Error('No guard node URL configured.');

  const controllers: AbortController[] = [];
  const attempts = bases.map(base => new Promise<DiscoveryResult>(async (resolve, reject) => {
    const controller = new AbortController();
    controllers.push(controller);
    const timeoutId = setTimeout(() => controller.abort(), 45000);
    try {
      const resp = await fetch(`${base}/discover`, {
        headers: { 'X-API-Key': apiKey },
        mode: 'cors',
        signal: controller.signal,
      });
      if (!resp.ok) {
        reject(new Error(`${base} returned ${resp.status}`));
        return;
      }
      const data = await resp.json();
      resolve({ nodes: data.nodes || [], ipCameras: data.ip_cameras || [] });
    } catch (e: any) {
      reject(e);
    } finally {
      clearTimeout(timeoutId);
    }
  }));

  try {
    return await Promise.any(attempts);
  } catch (e: any) {
    const first = e?.errors?.find((err: any) => err instanceof Error) as Error | undefined;
    throw first ?? new Error('No guard node reachable to run the scan.');
  } finally {
    controllers.forEach(c => c.abort());
  }
};

export const setGuardArmed = async (
  baseUrl: string,
  apiKey: string,
  armed: boolean
): Promise<boolean> => {
  const resp = await guardFetch(baseUrl, '/arm', apiKey, {
    method: 'POST',
    body: JSON.stringify({ armed }),
  });
  const data = await resp.json();
  return data.armed;
};

/** Tell a guard node to rebuild its camera list from the hardware plugged in
 * right now (/rescan), which also recovers a webcam stuck on black. Falls back
 * to /wake, which only reopens the same device indexes - enough for a stalled
 * camera, but not for one that was moved to a different USB port. Best-effort. */
export const wakeGuardCameras = async (
  baseUrl: string,
  apiKey: string
): Promise<void> => {
  try {
    await guardFetch(baseUrl, '/rescan', apiKey, { method: 'POST' });
    return;
  } catch {
    // guard predates /rescan - fall through to the plain wake
  }
  try {
    await guardFetch(baseUrl, '/wake', apiKey, { method: 'POST' });
  } catch {
    // older guards lack /wake too - the client stream reload still helps
  }
};
