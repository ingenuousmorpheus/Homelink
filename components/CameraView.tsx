
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  VideoOff, Shield, ShieldOff, Camera, RefreshCcw,
  AlertTriangle, X, Maximize2, Grid2x2, Radar, Zap, Volume2, VolumeX, MicOff
} from 'lucide-react';
import { ChatSettings, GuardStatus, GuardEvent, GuardCameraInfo } from '../types';
import {
  guardMediaUrl, fetchGuardStatus, fetchGuardEvents, setGuardArmed, discoverNodes, wakeGuardCameras
} from '../services/cameraService';
import { LiveAudioPlayer } from '../services/liveAudio';

interface CameraViewProps {
  settings: ChatSettings;
  setSettings?: React.Dispatch<React.SetStateAction<ChatSettings>>;
}

const MIN_SLOTS = 4;
const DISCOVERY_INTERVAL_MS = 60000;
// Long-lived MJPEG <img> streams stall in browsers after a while (the tile
// freezes or goes black while the camera is actually fine). Silently
// reconnecting every couple minutes keeps every feed self-healing.
const STREAM_REFRESH_MS = 120000;

interface GuardNode {
  url: string;
  label: string;          // short tag shown on tiles, e.g. AlienWare
}

interface NodeState {
  node: GuardNode;
  status: GuardStatus | null;
  error: string | null;
}

interface Tile {
  node: GuardNode;
  cam: GuardCameraInfo;
  /** position on the wall, 0-based */
  slot: number;
}

interface NodeEvent extends GuardEvent {
  node: GuardNode;
}

const pad2 = (n: number) => String(n).padStart(2, '0');

const formatClock = (d: Date) =>
  `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ` +
  `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;

const formatEventTime = (iso: string): string => {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return `${pad2(d.getMonth() + 1)}/${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
};

const cameraSortKey = (cam: GuardCameraInfo) =>
  `${cam.camera_ok ? '0' : '1'}-${String(cam.id).padStart(4, '0')}`;

const cleanNodeUrl = (url: string) => url.trim().replace(/\/$/, '');

const KNOWN_NODE_LABELS: Record<string, string> = {
  'http://100.110.73.8:7171': 'REDKRYPTONITE',
  'http://192.168.1.102:7171': 'REDKRYPTONITE',
  'http://100.115.8.121:7171': 'LENOVOMONITOR',
  'http://100.107.136.88:7171': 'ALIENWARE',
};

const labelForUrl = (url: string, fallbackIndex: number): string => {
  const cleaned = cleanNodeUrl(url);
  if (KNOWN_NODE_LABELS[cleaned]) return KNOWN_NODE_LABELS[cleaned];
  try {
    return new URL(cleaned).hostname.toUpperCase();
  } catch {
    return `N${fallbackIndex + 1}`;
  }
};

const nodesFromUrls = (urls: string[]): GuardNode[] =>
  Array.from(new Set(urls.map(cleanNodeUrl).filter(Boolean)))
    .map((url, i) => ({ url, label: labelForUrl(url, i) }));

const nodesFromSettings = (settings: ChatSettings): GuardNode[] =>
  nodesFromUrls(settings.cameraUrls || []);

const mergeUrls = (...lists: string[][]): string[] =>
  Array.from(new Set(lists.flat()
    .map(u => (u || '').trim())
    .filter(Boolean)
    .map(cleanNodeUrl)));

const urlsKey = (urls: string[]) => mergeUrls(urls).join('|');

const tileAudioKey = (tile: Tile): string => `${tile.node.url}|${tile.cam.id}`;
const hasMappedAudio = (tile: Tile): boolean => tile.cam.has_audio === true;

/** One CCTV tile: live MJPEG feed with CAM label, REC light, and timestamp. */
const CamTile: React.FC<{
  tile: Tile;
  apiKey: string;
  armed: boolean;
  clock: Date;
  nonce: number;
  large?: boolean;
  onClick?: () => void;
}> = ({ tile, apiKey, armed, clock, nonce, large, onClick }) => {
  const [failed, setFailed] = useState(false);
  const [retryTick, setRetryTick] = useState(0);
  const retryTimer = useRef<number | null>(null);

  const clearRetryTimer = () => {
    if (retryTimer.current !== null) {
      window.clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
  };

  const scheduleRetry = () => {
    setFailed(true);
    clearRetryTimer();
    retryTimer.current = window.setTimeout(() => {
      retryTimer.current = null;
      setFailed(false);
      setRetryTick(t => t + 1);
    }, 5000);
  };

  useEffect(() => {
    clearRetryTimer();
    setFailed(false);
    setRetryTick(t => t + 1);
    return clearRetryTimer;
  }, [nonce, tile.node.url, tile.cam.id, tile.cam.camera_ok]);

  return (
    <button
      onClick={onClick}
      className="relative w-full aspect-video overflow-hidden bg-black border border-[var(--border)] hover:border-[var(--border-bright)] transition-colors group text-left"
    >
      {tile.cam.camera_ok && !failed ? (
        <>
          <img
            key={`${tile.node.url}-${tile.cam.id}-${nonce}-${retryTick}`}
            src={guardMediaUrl(tile.node.url, '/stream', apiKey, { cam: tile.cam.id, cacheBust: nonce + retryTick })}
            alt={`Camera ${tile.slot + 1} live feed`}
            className="w-full h-full object-cover"
            onLoad={() => setFailed(false)}
            onError={scheduleRetry}
          />
          <div className="absolute inset-0 scanlines crt-vignette pointer-events-none" />
        </>
      ) : (
        <div className="absolute inset-0 tv-static flex flex-col items-center justify-center gap-2 bg-[#0a0a10]">
          <VideoOff className="w-8 h-8 text-[var(--dim)] opacity-50" />
          <span className="font-term text-[var(--amber)] text-xs tracking-[0.3em] flicker">SIGNAL LOST</span>
        </div>
      )}

      {/* HUD overlays */}
      <div className="absolute top-0 inset-x-0 flex items-center justify-between px-2 py-1 z-10">
        <span className="font-term text-[10px] tracking-[0.25em] text-[var(--gold)] bg-black/60 px-1.5 py-0.5">
          CAM {pad2(tile.slot + 1)} <span className="text-[var(--cyan)]">/ {tile.node.label}</span>
        </span>
        {armed && tile.cam.camera_ok && !failed && (
          <span className="flex items-center gap-1.5 bg-black/60 px-1.5 py-0.5">
            <span className="w-2 h-2 rounded-full bg-[var(--red)] rec-blink shadow-[0_0_8px_var(--red)]" />
            <span className="font-term text-[10px] text-[var(--red)] tracking-widest">REC</span>
          </span>
        )}
      </div>
      <div className="absolute bottom-0 inset-x-0 flex items-center justify-between px-2 py-1 z-10">
        <span className="font-term text-[10px] text-[var(--green)] bg-black/60 px-1.5 py-0.5 tracking-wider">
          {formatClock(clock)}
        </span>
        {!large && (
          <Maximize2 className="w-3.5 h-3.5 text-[var(--gold)] opacity-0 group-hover:opacity-100 transition-opacity" />
        )}
      </div>
    </button>
  );
};

/** Empty CCTV slot showing static. */
const EmptySlot: React.FC<{ slot: number }> = ({ slot }) => (
  <div className="relative w-full aspect-video overflow-hidden bg-[#0a0a10] border border-[var(--border)] opacity-70">
    <div className="absolute inset-0 tv-static" />
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-1">
      <span className="font-term text-[var(--dim)] text-xs tracking-[0.35em] flicker">NO SIGNAL</span>
      <span className="font-term text-[9px] text-[var(--dim)] opacity-60 tracking-[0.25em]">CH {pad2(slot + 1)}</span>
    </div>
    <span className="absolute top-1 left-2 font-term text-[10px] tracking-[0.25em] text-[var(--dim)]">
      CAM {pad2(slot + 1)}
    </span>
  </div>
);

export const CameraView: React.FC<CameraViewProps> = ({ settings, setSettings }) => {
  const [nodeStates, setNodeStates] = useState<NodeState[]>([]);
  const [discoveredUrls, setDiscoveredUrls] = useState<string[]>([]);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [lastDiscovery, setLastDiscovery] = useState<string | null>(null);
  const [events, setEvents] = useState<NodeEvent[]>([]);
  const [streamNonce, setStreamNonce] = useState(() => Date.now());
  const [isToggling, setIsToggling] = useState(false);
  const [focusedSlot, setFocusedSlot] = useState<number | null>(null);
  const [viewerEvent, setViewerEvent] = useState<NodeEvent | null>(null);
  // live audio: only the focused camera is ever audible, so you hear exactly
  // the one you tapped. Preference persists as you switch cameras.
  const [audioOn, setAudioOn] = useState(false);
  const [audioTileKey, setAudioTileKey] = useState<string | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const audioPlayerRef = useRef<LiveAudioPlayer | null>(null);
  const [clock, setClock] = useState(() => new Date());
  const isMounted = useRef(true);
  const discoveringRef = useRef(false);
  const dedupedNodesRef = useRef<GuardNode[]>([]);

  const { apiKey } = settings;
  const configuredUrls = (settings.cameraUrls || []).map(cleanNodeUrl).filter(Boolean);
  const nodes = nodesFromUrls(mergeUrls(configuredUrls, discoveredUrls));
  const nodesKey = nodes.map(n => n.url).join('|');

  const runDiscovery = useCallback(async () => {
    const baseUrls = nodes.map(n => n.url);
    if (baseUrls.length === 0 || discoveringRef.current) return;
    discoveringRef.current = true;
    setIsDiscovering(true);
    try {
      const result = await discoverNodes(baseUrls, apiKey);
      const foundUrls = result.nodes.map(n => n.url);
      setDiscoveredUrls(prev => {
        const merged = mergeUrls(prev, foundUrls);
        return urlsKey(merged) === urlsKey(prev) ? prev : merged;
      });
      if (foundUrls.length > 0) {
        setSettings?.(prev => {
          const merged = mergeUrls(prev.cameraUrls || [], foundUrls);
          return urlsKey(merged) === urlsKey(prev.cameraUrls || [])
            ? prev
            : { ...prev, cameraUrls: merged };
        });
      }
      const camCount = result.nodes.reduce((sum, node) => sum + node.cameras, 0);
      const newCount = foundUrls.filter(url => !nodes.some(n => n.url === cleanNodeUrl(url))).length;
      setLastDiscovery(
        `SCAN ${newCount > 0 ? 'EXPANDED' : 'CLEAR'} // ${result.nodes.length} NODE${result.nodes.length === 1 ? '' : 'S'} // ${camCount} CAMERA${camCount === 1 ? '' : 'S'}`
      );
    } catch (e: any) {
      setLastDiscovery(`SCAN FAILED // ${e.message || 'NO DISCOVERY NODE'}`);
    } finally {
      discoveringRef.current = false;
      setIsDiscovering(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodesKey, apiKey, setSettings]);

  const refreshStatus = useCallback(async () => {
    const states = await Promise.all(
      nodesFromUrls(mergeUrls(configuredUrls, discoveredUrls)).map(async (node): Promise<NodeState> => {
        try {
          const status = await fetchGuardStatus(node.url, apiKey);
          const label = status.node_id || status.hostname || node.label;
          return { node: { ...node, label: label.toUpperCase() }, status, error: null };
        } catch (e: any) {
          return { node, status: null, error: e.message };
        }
      })
    );
    // One machine can be reachable at two addresses (Tailscale + LAN) and
    // would show every camera twice. Dedupe by the node's reported identity,
    // preferring whichever address is online - and of two online addresses,
    // the Tailscale one so phones away from home can still load streams.
    const isTailscale = (u: string) => /\/\/100\./.test(u);
    const byIdentity = new Map<string, NodeState>();
    for (const st of states) {
      const identity = st.status?.node_id || st.status?.hostname || st.node.url;
      const prev = byIdentity.get(identity);
      if (!prev) { byIdentity.set(identity, st); continue; }
      const preferNew =
        (!prev.status && !!st.status) ||
        (!!prev.status && !!st.status && !isTailscale(prev.node.url) && isTailscale(st.node.url));
      if (preferNew) byIdentity.set(identity, st);
    }
    const deduped = Array.from(byIdentity.values());
    dedupedNodesRef.current = deduped.map(s => s.node);
    if (isMounted.current) setNodeStates(deduped);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodesKey, apiKey, discoveredUrls.join('|')]);

  const refreshEvents = useCallback(async () => {
    // pull events from the deduped node set (one address per machine)
    const eventNodes = dedupedNodesRef.current.length
      ? dedupedNodesRef.current
      : nodesFromUrls(mergeUrls(configuredUrls, discoveredUrls));
    const lists = await Promise.all(
      eventNodes.map(async (node): Promise<NodeEvent[]> => {
        try {
          const list = await fetchGuardEvents(node.url, apiKey);
          return list.map(e => ({ ...e, node }));
        } catch {
          return [];
        }
      })
    );
    if (isMounted.current) {
      setEvents(lists.flat().sort((a, b) => b.time.localeCompare(a.time)).slice(0, 24));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodesKey, apiKey, discoveredUrls.join('|')]);

  useEffect(() => {
    isMounted.current = true;
    refreshStatus();
    refreshEvents();
    runDiscovery();
    const statusInterval = setInterval(refreshStatus, 10000);
    const eventsInterval = setInterval(refreshEvents, 30000);
    const discoveryInterval = setInterval(runDiscovery, DISCOVERY_INTERVAL_MS);
    const clockInterval = setInterval(() => setClock(new Date()), 1000);
    // Self-heal: silently reconnect every stream on a timer so a stalled
    // MJPEG feed never stays black for more than a couple minutes.
    const streamRefresh = setInterval(() => {
      if (isMounted.current) setStreamNonce(Date.now());
    }, STREAM_REFRESH_MS);
    return () => {
      isMounted.current = false;
      clearInterval(statusInterval);
      clearInterval(eventsInterval);
      clearInterval(discoveryInterval);
      clearInterval(clockInterval);
      clearInterval(streamRefresh);
    };
  }, [refreshStatus, refreshEvents, runDiscovery]);

  const reloadStreams = () => {
    setStreamNonce(Date.now());
    refreshStatus();
    runDiscovery();
  };

  const [isWaking, setIsWaking] = useState(false);
  // WAKE: ask every node to re-detect its cameras (fixes a webcam stuck on
  // black AND one that moved to a different USB port), then reconnect all
  // browser streams once the devices have cycled.
  const wakeCameras = async () => {
    if (isWaking) return;
    setIsWaking(true);
    try {
      const urls: string[] = Array.from(new Set(onlineStates.map(s => s.node.url)));
      await Promise.all(urls.map((u: string) => wakeGuardCameras(u, apiKey)));
      // a rescan probes every USB index server-side, so give it longer than a
      // plain reopen before asking the browser to reconnect the streams
      await new Promise(r => setTimeout(r, 9000));
      setStreamNonce(Date.now());
      await refreshStatus();
    } finally {
      setIsWaking(false);
    }
  };

  const onlineStates = nodeStates.filter(s => s.status !== null);
  const offlineStates = nodeStates.filter(s => s.status === null);
  const anyOnline = onlineStates.length > 0;
  const armed = onlineStates.some(s => s.status!.armed);

  // STABLE ordering (node, then camera id) so CAM numbers never reshuffle -
  // a tile keeps its slot whether its camera is live or down.
  const tiles: Tile[] = nodeStates
    .flatMap(s => (s.status?.cameras ?? []).map(cam => ({ node: s.node, cam })))
    .sort((a, b) =>
      a.node.label.localeCompare(b.node.label) || (a.cam.id - b.cam.id)
    )
    .map((t, slot) => ({ ...t, slot }));

  // the wall always shows at least 4 channels, growing in pairs as cameras appear
  const slotCount = Math.max(MIN_SLOTS, Math.ceil(tiles.length / 2) * 2);

  const focused = focusedSlot !== null ? tiles.find(t => t.slot === focusedSlot) : undefined;
  const firstError = nodeStates.find(s => s.error)?.error;

  const toggleArmed = async () => {
    if (!anyOnline || isToggling) return;
    setIsToggling(true);
    try {
      await Promise.all(
        onlineStates.map(s => setGuardArmed(s.node.url, apiKey, !armed))
      );
      await refreshStatus();
    } finally {
      setIsToggling(false);
    }
  };

  // Only the focused camera is ever audible: starting a new stream always
  // stops the previous one, so you hear exactly the camera you tapped.
  const stopAudio = useCallback(() => {
    audioPlayerRef.current?.stop();
    audioPlayerRef.current = null;
    setAudioTileKey(null);
  }, []);

  const startAudio = useCallback((tile: Tile) => {
    setAudioError(null);
    stopAudio();
    const player = new LiveAudioPlayer(
      guardMediaUrl(tile.node.url, '/audio', apiKey,
                    { cam: tile.cam.id, cacheBust: Date.now() })
    );
    audioPlayerRef.current = player;
    setAudioTileKey(tileAudioKey(tile));
    setAudioOn(true);
    // click is the user gesture browsers require before audio may start
    void player.start(msg => {
      if (!isMounted.current) return;
      setAudioError(msg);
      setAudioOn(false);
      setAudioTileKey(null);
    });
  }, [apiKey, stopAudio]);

  const toggleAudio = (tile: Tile) => {
    if (audioOn && audioTileKey === tileAudioKey(tile)) {
      stopAudio();
      setAudioOn(false);
      return;
    }
    startAudio(tile);
  };

  const focusTile = (tile: Tile) => {
    setFocusedSlot(tile.slot);
    if (hasMappedAudio(tile)) {
      startAudio(tile);
    } else {
      stopAudio();
      setAudioOn(false);
      setAudioError(null);
    }
  };

  // leaving the focused view (or unmounting) always silences audio
  useEffect(() => {
    if (focusedSlot === null) {
      stopAudio();
      setAudioOn(false);
      setAudioError(null);
    }
  }, [focusedSlot, stopAudio]);

  useEffect(() => stopAudio, [stopAudio]);

  const openSnapshot = (tile: Tile) => {
    window.open(
      guardMediaUrl(tile.node.url, '/snapshot', apiKey, { cam: tile.cam.id, cacheBust: Date.now(), save: true }),
      '_blank'
    );
  };

  const maxUptime = Math.max(0, ...onlineStates.map(s => s.status!.uptime_seconds));
  const uptimeLabel = (() => {
    const h = Math.floor(maxUptime / 3600);
    const m = Math.floor((maxUptime % 3600) / 60);
    return h > 0 ? `${h}H ${m}M` : `${m}M`;
  })();
  const focusedAudioOn = !!focused && audioOn && audioTileKey === tileAudioKey(focused);

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* Monitor frame */}
      <div className="border border-[var(--border)] bg-[var(--panel)] backdrop-blur-md">
        {/* Monitor header bar */}
        <div className="flex items-center justify-between px-4 h-10 border-b border-[var(--border)]">
          <div className="flex items-center gap-3">
            <span className="font-cyber text-[11px] font-bold tracking-[0.3em] text-[var(--gold)] glow-gold">
              SENTINEL GRID
            </span>
            <span className={`font-term text-[10px] tracking-widest ${anyOnline ? 'text-[var(--green)] glow-green' : 'text-[var(--red)] glow-red'}`}>
              ONLINE NODES {onlineStates.length}/{nodes.length}
            </span>
          </div>
          <div className="flex items-center gap-4 font-term text-[10px] text-[var(--dim)] tracking-wider">
            {anyOnline && <span>UPTIME {uptimeLabel}</span>}
            <span className="hidden sm:inline text-[var(--cyan)]">{tiles.length} FEED{tiles.length === 1 ? '' : 'S'}</span>
          </div>
        </div>

        {/* Camera wall */}
        <div className="p-2">
          {!anyOnline ? (
            <div className="relative aspect-video tv-static bg-[#0a0a10] border border-[var(--border)] flex flex-col items-center justify-center gap-4 px-8 text-center">
              <VideoOff className="w-12 h-12 text-[var(--dim)] opacity-40" />
              <p className="font-term text-xs text-[var(--amber)] tracking-wider leading-relaxed max-w-md flicker">
                {firstError || 'ESTABLISHING UPLINK...'}
              </p>
              <button
                onClick={reloadStreams}
                className="px-5 py-2 border border-[var(--border-bright)] text-[var(--gold)] font-cyber text-[10px] tracking-[0.25em] hover:bg-[rgba(255,184,90,.08)] active:scale-95 transition-all"
              >
                RECONNECT
              </button>
            </div>
          ) : focused ? (
            /* Focused single-camera view */
            <div className="space-y-2">
              <CamTile
                tile={focused}
                apiKey={apiKey}
                armed={armed}
                clock={clock}
                nonce={streamNonce}
                large
                onClick={() => hasMappedAudio(focused) && toggleAudio(focused)}
              />
              <div className="flex gap-2">
                <button
                  onClick={() => setFocusedSlot(null)}
                  className="flex-1 py-2.5 border border-[var(--border-bright)] text-[var(--gold)] font-cyber text-[10px] tracking-[0.25em] flex items-center justify-center gap-2 hover:bg-[rgba(255,184,90,.08)] active:scale-95 transition-all"
                >
                  <Grid2x2 className="w-3.5 h-3.5" /> GRID VIEW
                </button>
                <button
                  onClick={() => toggleAudio(focused)}
                  disabled={!hasMappedAudio(focused)}
                  title={focused.cam.audio_device || undefined}
                  className={`flex-1 py-2.5 border font-cyber text-[10px] tracking-[0.25em] flex items-center justify-center gap-2 active:scale-95 transition-all ${
                    !hasMappedAudio(focused)
                      ? 'border-[var(--border)] text-[var(--dim)] opacity-40'
                      : focusedAudioOn
                        ? 'border-[var(--green)] text-[var(--green)] bg-[rgba(122,255,176,.08)]'
                        : 'border-[var(--border)] text-[var(--gold)] hover:bg-[rgba(255,184,90,.08)]'
                  }`}
                >
                  {!hasMappedAudio(focused)
                    ? <><MicOff className="w-3.5 h-3.5" /> NO MIC</>
                    : focusedAudioOn
                      ? <><Volume2 className="w-3.5 h-3.5" /> LISTENING</>
                      : <><VolumeX className="w-3.5 h-3.5" /> LISTEN</>}
                </button>
                <button
                  onClick={() => openSnapshot(focused)}
                  className="flex-1 py-2.5 border border-[var(--border)] text-[var(--cyan)] font-cyber text-[10px] tracking-[0.25em] flex items-center justify-center gap-2 hover:bg-[rgba(92,200,255,.08)] active:scale-95 transition-all"
                >
                  <Camera className="w-3.5 h-3.5" /> CAPTURE
                </button>
              </div>

              {audioError && (
                <p className="font-term text-[10px] text-[var(--red)] tracking-wider px-1">
                  AUDIO // {audioError}
                </p>
              )}
            </div>
          ) : (
            /* 4-way CCTV wall */
            <div className="grid grid-cols-2 gap-2">
              {Array.from({ length: slotCount }, (_, slot) => {
                const tile = tiles.find(t => t.slot === slot);
                return tile ? (
                  <CamTile
                    key={`${tile.node.url}-${tile.cam.id}`}
                    tile={tile}
                    apiKey={apiKey}
                    armed={armed}
                    clock={clock}
                    nonce={streamNonce}
                    onClick={() => focusTile(tile)}
                  />
                ) : (
                  <EmptySlot key={`empty-${slot}`} slot={slot} />
                );
              })}
            </div>
          )}
        </div>

        {/* Control deck */}
        <div className="grid grid-cols-5 divide-x divide-[var(--border)] border-t border-[var(--border)]">
          <button
            onClick={toggleArmed}
            disabled={!anyOnline || isToggling}
            className={`py-3.5 flex flex-col items-center gap-1 transition-colors ${
              !anyOnline ? 'text-[var(--dim)] opacity-40' : armed ? 'text-[var(--green)]' : 'text-[var(--dim)]'
            }`}
          >
            {armed ? <Shield className="w-5 h-5" /> : <ShieldOff className="w-5 h-5" />}
            <span className="font-cyber text-[9px] tracking-[0.25em]">
              {!anyOnline ? 'OFFLINE' : isToggling ? '...' : armed ? 'ARMED' : 'DISARMED'}
            </span>
          </button>
          <button
            onClick={() => tiles[0] && openSnapshot(focused ?? tiles[0])}
            disabled={tiles.length === 0}
            className={`py-3.5 flex flex-col items-center gap-1 ${tiles.length > 0 ? 'text-[var(--cyan)]' : 'text-[var(--dim)] opacity-40'}`}
          >
            <Camera className="w-5 h-5" />
            <span className="font-cyber text-[9px] tracking-[0.25em]">CAPTURE</span>
          </button>
          <button
            onClick={wakeCameras}
            disabled={!anyOnline || isWaking}
            className={`py-3.5 flex flex-col items-center gap-1 ${isWaking ? 'text-[var(--green)]' : 'text-[var(--red)]'} disabled:text-[var(--dim)] disabled:opacity-40`}
          >
            <Zap className={`w-5 h-5 ${isWaking ? 'animate-pulse' : ''}`} />
            <span className="font-cyber text-[9px] tracking-[0.25em]">{isWaking ? 'WAKING' : 'WAKE'}</span>
          </button>
          <button onClick={reloadStreams} className="py-3.5 flex flex-col items-center gap-1 text-[var(--gold)]">
            <RefreshCcw className="w-5 h-5" />
            <span className="font-cyber text-[9px] tracking-[0.25em]">RESYNC</span>
          </button>
          <button
            onClick={runDiscovery}
            disabled={isDiscovering || nodes.length === 0}
            className={`py-3.5 flex flex-col items-center gap-1 ${isDiscovering ? 'text-[var(--cyan)]' : 'text-[var(--gold)]'} disabled:text-[var(--dim)] disabled:opacity-40`}
          >
            {isDiscovering ? <RefreshCcw className="w-5 h-5 animate-spin" /> : <Radar className="w-5 h-5" />}
            <span className="font-cyber text-[9px] tracking-[0.25em]">SCAN</span>
          </button>
        </div>
      </div>

      {lastDiscovery && (
        <p className="font-term text-[10px] tracking-[0.2em] text-[var(--cyan)] px-1">
          {lastDiscovery}
        </p>
      )}

      {offlineStates.length > 0 && (
        <div className="border border-[rgba(255,59,92,.35)] bg-[rgba(255,59,92,.05)] px-3 py-2">
          <p className="font-term text-[10px] text-[var(--red)] tracking-wider leading-relaxed">
            OFFLINE NODE{offlineStates.length === 1 ? '' : 'S'} // {offlineStates.map(s => s.node.label).join(' // ')}
          </p>
        </div>
      )}

      {/* Motion log */}
      <div className="border border-[var(--border)] bg-[var(--panel)] backdrop-blur-md">
        <div className="flex items-center justify-between px-4 h-10 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-[var(--amber)]" />
            <span className="font-cyber text-[11px] font-bold tracking-[0.3em] text-[var(--amber)]">MOTION LOG</span>
            {events.length > 0 && (
              <span className="font-term text-[10px] text-[var(--red)] border border-[var(--red)] px-1.5 leading-4">
                {events.length}
              </span>
            )}
          </div>
          <button onClick={refreshEvents} className="p-1.5 text-[var(--dim)] hover:text-[var(--gold)] transition-colors">
            <RefreshCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        {events.length === 0 ? (
          <div className="py-8 flex flex-col items-center gap-2">
            <p className="font-term text-[11px] text-[var(--dim)] tracking-[0.2em]">
              {!anyOnline ? '// LINK DOWN - NO DATA //' : armed ? '// ALL QUIET - NO INTRUSIONS //' : '// DETECTION DISARMED //'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 p-2">
            {events.map(event => (
              <button
                key={`${event.node.url}-${event.name}`}
                onClick={() => setViewerEvent(event)}
                className="relative overflow-hidden bg-black aspect-video border border-[var(--border)] hover:border-[var(--red)] group active:scale-95 transition-all"
              >
                <img
                  src={guardMediaUrl(event.node.url, `/events/${event.name}`, apiKey)}
                  alt={`Motion on ${event.node.label} camera ${event.cam + 1} at ${formatEventTime(event.time)}`}
                  loading="lazy"
                  className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                />
                <div className="absolute bottom-0 inset-x-0 bg-black/75 px-1.5 py-1 flex items-center justify-between">
                  <span className="font-term text-[9px] text-[var(--red)]">{event.node.label}/C{pad2(event.cam + 1)}</span>
                  <span className="font-term text-[9px] text-[var(--gold)]">{formatEventTime(event.time)}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Full-screen event viewer */}
      {viewerEvent && (
        <div
          className="fixed inset-0 z-50 bg-black/95 flex flex-col items-center justify-center p-4"
          onClick={() => setViewerEvent(null)}
        >
          <button className="absolute top-4 right-4 p-2 text-[var(--dim)] hover:text-[var(--gold)]">
            <X className="w-7 h-7" />
          </button>
          <div className="relative scanlines border border-[var(--border-bright)]" onClick={e => e.stopPropagation()}>
            <img
              src={guardMediaUrl(viewerEvent.node.url, `/events/${viewerEvent.name}`, apiKey)}
              alt={`Motion on ${viewerEvent.node.label} camera ${viewerEvent.cam + 1} at ${formatEventTime(viewerEvent.time)}`}
              className="max-w-full max-h-[80vh]"
            />
          </div>
          <p className="mt-4 font-term text-xs text-[var(--amber)] tracking-[0.2em] flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-[var(--red)]" />
            INTRUSION // {viewerEvent.node.label} / CAM {pad2(viewerEvent.cam + 1)} // {formatEventTime(viewerEvent.time)}
          </p>
        </div>
      )}
    </div>
  );
};
