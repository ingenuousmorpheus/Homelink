
import React, { useState } from 'react';
import { ChatSettings, LMStudioModel } from '../types';
import { X, RefreshCcw, CheckCircle2, Activity, AlertTriangle, ShieldCheck, Wifi, Laptop, ExternalLink, Info, ShieldQuestion, Video, Radar } from 'lucide-react';
import { discoverNodes } from '../services/cameraService';

interface SettingsModalProps {
  settings: ChatSettings;
  setSettings: (s: ChatSettings) => void;
  onClose: () => void;
}

const inputClass = 'flex-1 px-4 py-3 border border-[var(--border)] bg-black/40 font-term text-xs text-[var(--text)] focus:border-[var(--border-bright)] focus:outline-none';
const labelClass = 'font-cyber text-[9px] text-[var(--dim)] tracking-[0.3em] px-1 flex items-center gap-1.5';

export const SettingsModal: React.FC<SettingsModalProps> = ({ settings, setSettings, onClose }) => {
  const [localSettings, setLocalSettings] = useState(settings);
  const [models, setModels] = useState<LMStudioModel[]>([]);
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
  const [nodesText, setNodesText] = useState((settings.cameraUrls || []).join('\n'));
  const [nodeResults, setNodeResults] = useState<{ url: string; ok: boolean; detail: string }[] | null>(null);
  const [nodesTesting, setNodesTesting] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanSummary, setScanSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTroubleshooting, setShowTroubleshooting] = useState(false);

  const CORRECT_IP = "100.107.136.88";

  const useLocal = () => {
    setLocalSettings(prev => ({ ...prev, serverUrl: `http://localhost:6969` }));
    setTestStatus('idle');
    setError(null);
  };

  const useTailscale = () => {
    setLocalSettings(prev => ({ ...prev, serverUrl: `http://${CORRECT_IP}:6969` }));
    setTestStatus('idle');
    setError(null);
  };

  const testInNewTab = () => {
    window.open(`${localSettings.serverUrl}/`, '_blank');
  };

  const performDiagnostic = async () => {
    if (!localSettings.serverUrl) {
      setError("Please enter a Proxy URL.");
      setTestStatus('error');
      return;
    }

    setTestStatus('testing');
    setError(null);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const url = localSettings.serverUrl.replace(/\/$/, '');
      const resp = await fetch(`${url}/models`, {
        method: 'GET',
        headers: { 'X-API-Key': localSettings.apiKey, 'Accept': 'application/json' },
        mode: 'cors',
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (resp.ok) {
        const data = await resp.json();
        setModels(data.data || []);
        setTestStatus('success');
      } else {
        setTestStatus('error');
        setError(resp.status === 403 ? "Secret Key mismatch." : `Server Error: ${resp.status}`);
      }
    } catch (e: any) {
      clearTimeout(timeoutId);
      setTestStatus('error');
      setShowTroubleshooting(true);
      setError(`CONNECTION REFUSED. Check Chrome Permissions for Port 6969.`);
    }
  };

  const parseNodes = (text: string): string[] =>
    Array.from(new Set(text.split(/[\n,]+/).map(u => u.trim()).filter(Boolean)));

  const scanNetwork = async () => {
    setScanning(true);
    setScanSummary(null);
    setNodeResults(null);
    try {
      const known = parseNodes(nodesText);
      const { nodes: found, ipCameras } = await discoverNodes(known, localSettings.apiKey);
      const merged = Array.from(new Set([...known, ...found.map(n => n.url)]));
      setNodesText(merged.join('\n'));
      const added = merged.length - known.length;
      const totalCams = found.reduce((sum, n) => sum + n.cameras, 0);
      setScanSummary(
        `SCAN COMPLETE // ${found.length} NODE${found.length === 1 ? '' : 'S'}, ${totalCams} CAMERA${totalCams === 1 ? '' : 'S'} FOUND` +
        (added > 0 ? ` // ${added} NEW NODE${added === 1 ? '' : 'S'} ADDED` : ' // NO NEW NODES') +
        (ipCameras.length > 0 ? ` // ${ipCameras.length} STANDALONE IP CAM${ipCameras.length === 1 ? '' : 'S'} DETECTED` : '')
      );
      setNodeResults([
        ...found.map(n => ({
          url: n.url,
          ok: n.cameras > 0,
          detail: n.cameras > 0 ? `ONLINE // ${n.cameras} CAMERA${n.cameras === 1 ? '' : 'S'}` : 'ONLINE BUT NO WORKING CAMERA',
        })),
        ...ipCameras.map(c => ({
          url: c.ip,
          ok: true,
          detail: 'ONVIF IP CAMERA // NEEDS ITS RTSP URL + PASSWORD IN guard_cameras.json',
        })),
      ]);
    } catch (e: any) {
      setScanSummary(`SCAN FAILED // ${e.message}`);
    } finally {
      setScanning(false);
    }
  };

  const testNodes = async () => {
    const urls = parseNodes(nodesText);
    if (urls.length === 0) {
      setNodeResults([{ url: '(none)', ok: false, detail: 'No node URLs entered.' }]);
      return;
    }
    setNodesTesting(true);
    const results = await Promise.all(urls.map(async url => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      try {
        const resp = await fetch(`${url.replace(/\/$/, '')}/`, {
          method: 'GET',
          headers: { 'X-API-Key': localSettings.apiKey, 'Accept': 'application/json' },
          mode: 'cors',
          signal: controller.signal,
        });
        clearTimeout(timeoutId);
        if (!resp.ok) {
          return { url, ok: false, detail: resp.status === 403 ? 'SECRET MISMATCH' : `ERROR ${resp.status}` };
        }
        const data = await resp.json();
        const cams = (data.cameras || []).filter((c: any) => c.camera_ok).length;
        return cams > 0
          ? { url, ok: true, detail: `ONLINE // ${cams} CAMERA${cams === 1 ? '' : 'S'}` }
          : { url, ok: false, detail: 'ONLINE BUT NO WORKING CAMERA' };
      } catch {
        clearTimeout(timeoutId);
        return { url, ok: false, detail: 'UNREACHABLE' };
      }
    }));
    setNodeResults(results);
    setNodesTesting(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/80 backdrop-blur-sm">
      <div className="bg-[var(--panel-solid)] border border-[var(--border-bright)] w-full max-w-lg shadow-[0_0_60px_rgba(255,184,90,.12)] overflow-hidden flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between p-5 border-b border-[var(--border)] shrink-0">
          <div className="flex items-center gap-2">
            <ShieldCheck className={`w-4 h-4 ${testStatus === 'success' ? 'text-[var(--green)]' : 'text-[var(--dim)]'}`} />
            <h2 className="font-cyber text-xs font-bold tracking-[0.3em] text-[var(--gold)] glow-gold">SYSTEM CONFIG</h2>
          </div>
          <button onClick={onClose} className="p-2 text-[var(--dim)] hover:text-[var(--gold)]">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-5 overflow-y-auto">
          {/* Quick Setup Presets */}
          <div className="flex gap-2">
            <button onClick={useLocal} className={`flex-1 flex flex-col items-center py-3 border font-cyber text-[9px] tracking-[0.2em] transition-all ${localSettings.serverUrl.includes('localhost') ? 'border-[var(--cyan)] text-[var(--cyan)] bg-[rgba(92,200,255,.08)]' : 'border-[var(--border)] text-[var(--dim)]'}`}>
              <Laptop className="w-4 h-4 mb-1" /> SAME MACHINE
            </button>
            <button onClick={useTailscale} className={`flex-1 flex flex-col items-center py-3 border font-cyber text-[9px] tracking-[0.2em] transition-all ${localSettings.serverUrl.includes(CORRECT_IP) ? 'border-[var(--cyan)] text-[var(--cyan)] bg-[rgba(92,200,255,.08)]' : 'border-[var(--border)] text-[var(--dim)]'}`}>
              <Wifi className="w-4 h-4 mb-1" /> TAILSCALE (PC)
            </button>
          </div>

          <div className="space-y-2">
            <label className={labelClass}>NEURAL PROXY URL</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={localSettings.serverUrl}
                onChange={e => setLocalSettings(prev => ({ ...prev, serverUrl: e.target.value }))}
                className={inputClass}
              />
              <button onClick={performDiagnostic} disabled={testStatus === 'testing'} className="px-4 border border-[rgba(92,200,255,.4)] text-[var(--cyan)] hover:bg-[rgba(92,200,255,.08)] active:scale-95 transition-all">
                {testStatus === 'testing' ? <RefreshCcw className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Sentinel nodes - one guard server URL per line */}
          <div className="space-y-2 pt-3 border-t border-[var(--border)]">
            <label className={labelClass}>
              <Video className="w-3 h-3" /> SENTINEL NODES (ONE PER LINE)
            </label>
            <div className="flex gap-2">
              <textarea
                rows={3}
                value={nodesText}
                onChange={e => {
                  setNodesText(e.target.value);
                  setNodeResults(null);
                }}
                placeholder={'http://100.110.73.8:7171\nhttp://100.107.136.88:7171'}
                className={`${inputClass} resize-none leading-relaxed`}
              />
              <button onClick={testNodes} disabled={nodesTesting} className="px-4 border border-[rgba(255,59,92,.4)] text-[var(--red)] hover:bg-[rgba(255,59,92,.08)] active:scale-95 transition-all">
                {nodesTesting ? <RefreshCcw className="w-4 h-4 animate-spin" /> : <Video className="w-4 h-4" />}
              </button>
            </div>
            <button
              onClick={scanNetwork}
              disabled={scanning}
              className="w-full py-2.5 border border-[rgba(92,200,255,.4)] text-[var(--cyan)] font-cyber text-[10px] tracking-[0.25em] flex items-center justify-center gap-2 hover:bg-[rgba(92,200,255,.08)] active:scale-95 transition-all disabled:opacity-50"
            >
              {scanning
                ? <><RefreshCcw className="w-3.5 h-3.5 animate-spin" /> SCANNING NETWORK...</>
                : <><Radar className="w-3.5 h-3.5" /> SCAN NETWORK FOR CAMERAS</>}
            </button>
            {scanSummary && (
              <p className={`font-term text-[10px] px-1 tracking-wider ${scanSummary.startsWith('SCAN FAILED') ? 'text-[var(--red)]' : 'text-[var(--cyan)]'}`}>
                {scanSummary}
              </p>
            )}
            {nodeResults && (
              <div className="space-y-1.5">
                {nodeResults.map(r => (
                  <div key={r.url} className={`p-2.5 border flex items-start gap-2.5 ${r.ok ? 'border-[rgba(122,255,176,.3)] bg-[rgba(122,255,176,.05)]' : 'border-[rgba(255,59,92,.3)] bg-[rgba(255,59,92,.05)]'}`}>
                    {r.ok
                      ? <CheckCircle2 className="w-3.5 h-3.5 text-[var(--green)] shrink-0 mt-0.5" />
                      : <AlertTriangle className="w-3.5 h-3.5 text-[var(--red)] shrink-0 mt-0.5" />}
                    <span className={`font-term text-[10px] leading-relaxed break-all ${r.ok ? 'text-[var(--green)]' : 'text-[var(--red)]'}`}>
                      {r.url} — {r.detail}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <p className="font-term text-[9px] text-[var(--dim)] px-1 leading-relaxed tracking-wider">
              // EVERY CAMERA ON EVERY NODE MERGES ONTO THE SENTINEL GRID // ADD A MACHINE: RUN THE GUARD SETUP ON IT, PASTE ITS URL HERE //
            </p>
          </div>

          {testStatus === 'success' ? (
            <div className="p-3 border border-[rgba(122,255,176,.3)] bg-[rgba(122,255,176,.05)] flex items-center gap-3">
              <CheckCircle2 className="w-4 h-4 text-[var(--green)]" />
              <span className="font-term text-[11px] text-[var(--green)] tracking-wider">VERIFIED // ALIENWARE REACHABLE</span>
            </div>
          ) : error ? (
            <div className="p-4 border border-[rgba(255,59,92,.3)] bg-[rgba(255,59,92,.05)] space-y-3">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-4 h-4 text-[var(--red)] shrink-0 mt-0.5" />
                <span className="font-term text-[10px] text-[var(--red)] leading-relaxed">{error}</span>
              </div>

              <div className="pt-2 border-t border-[rgba(255,59,92,.2)] flex gap-2">
                <button
                  onClick={testInNewTab}
                  className="flex-1 py-2 border border-[rgba(255,59,92,.4)] font-cyber text-[9px] tracking-[0.2em] text-[var(--red)] flex items-center justify-center gap-2 hover:bg-[rgba(255,59,92,.08)] transition-colors"
                >
                  <ExternalLink className="w-3 h-3" /> STEP 1: OPEN
                </button>
                <button
                  onClick={() => setShowTroubleshooting(!showTroubleshooting)}
                  className="flex-1 py-2 bg-[rgba(255,59,92,.15)] border border-[var(--red)] font-cyber text-[9px] tracking-[0.2em] text-[var(--red)] flex items-center justify-center gap-2"
                >
                  <ShieldQuestion className="w-3 h-3" /> STEP 2: FIX
                </button>
              </div>
            </div>
          ) : null}

          {showTroubleshooting && (
            <div className="p-4 border border-[var(--border)] bg-black/50 space-y-4">
              <h3 className="font-cyber text-[10px] font-bold text-[var(--cyan)] tracking-[0.25em] flex items-center gap-2">
                <Info className="w-3.5 h-3.5" /> FINAL FIX REQUIRED
              </h3>

              <div className="space-y-3 font-term text-[10px] text-[var(--dim)] leading-relaxed tracking-wide">
                <div className="flex gap-3">
                  <span className="shrink-0 w-5 h-5 border border-[var(--cyan)] flex items-center justify-center text-[var(--cyan)]">1</span>
                  <p>Tap <b className="text-[var(--text)]">"STEP 1: OPEN"</b>. A white page appears saying <span className="text-[var(--green)]">{"{status: online}"}</span>.</p>
                </div>
                <div className="flex gap-3">
                  <span className="shrink-0 w-5 h-5 border border-[var(--cyan)] flex items-center justify-center text-[var(--cyan)]">2</span>
                  <p><b className="text-[var(--text)]">On that page</b>, tap the Lock icon in the browser bar → <b className="text-[var(--text)]">Site Settings</b>.</p>
                </div>
                <div className="flex gap-3">
                  <span className="shrink-0 w-5 h-5 border border-[var(--cyan)] flex items-center justify-center text-[var(--cyan)]">3</span>
                  <p>Set <b className="text-[var(--text)]">"Insecure Content"</b> to <b className="text-[var(--text)]">Allow</b>.</p>
                </div>
                <div className="flex gap-3">
                  <span className="shrink-0 w-5 h-5 border border-[var(--green)] flex items-center justify-center text-[var(--green)]">4</span>
                  <p className="text-[var(--green)]">Come back and re-test. The light goes GREEN.</p>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="p-5 border-t border-[var(--border)] flex gap-3 shrink-0">
          <button onClick={onClose} className="flex-1 py-3 font-cyber text-[10px] tracking-[0.25em] text-[var(--dim)]">CANCEL</button>
          <button
            onClick={() => { setSettings({ ...localSettings, cameraUrls: parseNodes(nodesText) }); onClose(); }}
            className="flex-1 py-3 border border-[var(--border-bright)] bg-[rgba(255,184,90,.1)] font-cyber text-[10px] tracking-[0.25em] text-[var(--gold)] shadow-[0_0_20px_rgba(255,184,90,.15)] active:scale-95 transition-transform"
          >
            SAVE &amp; LINK
          </button>
        </div>
      </div>
    </div>
  );
};
