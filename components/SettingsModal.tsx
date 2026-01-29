
import React, { useState } from 'react';
import { ChatSettings, LMStudioModel } from '../types';
import { X, Key, Brain, RefreshCcw, CheckCircle2, Activity, AlertTriangle, ShieldCheck, Wifi, Terminal, Laptop, ShieldAlert, ExternalLink, Info, ShieldQuestion, ArrowRight } from 'lucide-react';

interface SettingsModalProps {
  settings: ChatSettings;
  setSettings: (s: ChatSettings) => void;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ settings, setSettings, onClose }) => {
  const [localSettings, setLocalSettings] = useState(settings);
  const [models, setModels] = useState<LMStudioModel[]>([]);
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [showTroubleshooting, setShowTroubleshooting] = useState(false);

  const isHttps = window.location.protocol === 'https:';
  const isTargetHttp = localSettings.serverUrl.startsWith('http:');
  const needsBypass = isHttps && isTargetHttp;
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

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-900/60 backdrop-blur-sm">
      <div className="bg-white w-full max-w-lg rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden animate-in slide-in-from-bottom duration-300 flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between p-6 border-b border-slate-100 shrink-0">
          <div className="flex items-center gap-2">
            <ShieldCheck className={`w-5 h-5 ${testStatus === 'success' ? 'text-green-500' : 'text-slate-400'}`} />
            <h2 className="text-xl font-bold text-slate-800">Alienware Connection</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-full">
            <X className="w-6 h-6 text-slate-400" />
          </button>
        </div>

        <div className="p-6 space-y-5 overflow-y-auto">
          {/* Quick Setup Presets */}
          <div className="flex gap-2">
            <button onClick={useLocal} className={`flex-1 flex flex-col items-center py-3 rounded-xl text-[10px] font-bold transition-all ${localSettings.serverUrl.includes('localhost') ? 'bg-blue-600 text-white shadow-lg' : 'bg-slate-100 text-slate-500'}`}>
              <Laptop className="w-4 h-4 mb-1" /> Same Machine
            </button>
            <button onClick={useTailscale} className={`flex-1 flex flex-col items-center py-3 rounded-xl text-[10px] font-bold transition-all ${localSettings.serverUrl.includes(CORRECT_IP) ? 'bg-blue-600 text-white shadow-lg' : 'bg-slate-100 text-slate-500'}`}>
              <Wifi className="w-4 h-4 mb-1" /> Tailscale (PC)
            </button>
          </div>

          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest px-1">Proxy Server URL</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={localSettings.serverUrl}
                  onChange={e => setLocalSettings(prev => ({ ...prev, serverUrl: e.target.value }))}
                  className="flex-1 px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-mono text-xs focus:ring-2 focus:ring-blue-500/20 outline-none"
                />
                <button onClick={performDiagnostic} disabled={testStatus === 'testing'} className="px-4 bg-blue-600 text-white rounded-xl shadow-md active:scale-95 transition-all">
                  {testStatus === 'testing' ? <RefreshCcw className="w-5 h-5 animate-spin" /> : <Activity className="w-5 h-5" />}
                </button>
              </div>
            </div>
          </div>

          {testStatus === 'success' ? (
            <div className="p-3 bg-green-50 border border-green-100 rounded-xl flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-green-500" />
              <span className="text-xs font-bold text-green-700">Verified! PC is reachable.</span>
            </div>
          ) : error ? (
            <div className="p-4 bg-red-50 border border-red-100 rounded-2xl space-y-3">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                <span className="text-[11px] font-medium text-red-700 leading-tight">{error}</span>
              </div>
              
              <div className="pt-2 border-t border-red-100 flex gap-2">
                <button 
                  onClick={testInNewTab}
                  className="flex-1 py-2 bg-white border border-red-200 rounded-lg text-[10px] font-bold text-red-600 flex items-center justify-center gap-2 hover:bg-red-50 transition-colors"
                >
                  <ExternalLink className="w-3 h-3" /> Step 1: Click Me
                </button>
                <button 
                  onClick={() => setShowTroubleshooting(!showTroubleshooting)}
                  className="flex-1 py-2 bg-red-600 text-white rounded-lg text-[10px] font-bold flex items-center justify-center gap-2"
                >
                  <ShieldQuestion className="w-3 h-3" /> Step 2: Read Fix
                </button>
              </div>
            </div>
          ) : null}

          {showTroubleshooting && (
            <div className="p-5 bg-slate-900 rounded-2xl text-white space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
              <h3 className="text-xs font-bold text-blue-400 uppercase flex items-center gap-2">
                <Info className="w-4 h-4" /> Final Fix Required
              </h3>
              
              <div className="space-y-4">
                <div className="bg-slate-800 p-3 rounded-xl border border-amber-500/30">
                  <p className="text-[10px] text-amber-400 font-bold mb-2 uppercase">⚠️ The Port Problem</p>
                  <p className="text-[10px] text-slate-300 leading-relaxed">
                    In your screenshot, you allowed port <span className="text-white font-mono">8000</span>.
                    But the app is using <span className="text-white font-mono">6969</span>.
                  </p>
                </div>

                <div className="space-y-3 text-[10px]">
                  <div className="flex gap-3">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold">1</span>
                    <p className="text-slate-300">Click the <b>"Step 1: Click Me"</b> button above. It will open a white page that says <span className="font-mono">{"{status: online}"}</span>.</p>
                  </div>
                  <div className="flex gap-3">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold">2</span>
                    <p className="text-slate-300"><b>On that white page</b>, click the "Lock" icon in your browser bar. Go to <b>Site Settings</b>.</p>
                  </div>
                  <div className="flex gap-3">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold">3</span>
                    <p className="text-slate-300">Change <b>"Insecure Content"</b> to <b>"Allow"</b> for port <b>6969</b>. (Your previous fix was only for 8000).</p>
                  </div>
                  <div className="flex gap-3">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-green-600 flex items-center justify-center text-white font-bold">4</span>
                    <p className="text-slate-300 font-bold text-green-400">Come back here and refresh. It will turn GREEN!</p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="p-6 bg-slate-50 border-t border-slate-100 flex gap-3 shrink-0">
          <button onClick={onClose} className="flex-1 py-3 text-slate-500 font-bold text-sm">Cancel</button>
          <button onClick={() => { setSettings(localSettings); onClose(); }} className="flex-1 py-3 bg-blue-600 text-white rounded-2xl font-bold text-sm shadow-xl shadow-blue-200 transition-transform active:scale-95">Save & Connect</button>
        </div>
      </div>
    </div>
  );
};
