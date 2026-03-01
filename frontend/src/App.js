import { useState, useEffect, useCallback } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import axios from "axios";
import { Terminal, Shield, Settings, Lock, Activity, FileText, Trash2, Play, Square, RefreshCw, Upload } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Dashboard Component
const Dashboard = () => {
  const [settings, setSettings] = useState({ bot_token: "", chat_id: "" });
  const [status, setStatus] = useState({ is_running: false, bot_token_set: false, chat_id_set: false });
  const [attempts, setAttempts] = useState([]);
  const [activeTab, setActiveTab] = useState("status");
  const [loading, setLoading] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [tempSettings, setTempSettings] = useState({ bot_token: "", chat_id: "" });
  
  // Manual crack states
  const [selectedFile, setSelectedFile] = useState(null);
  const [crackName, setCrackName] = useState("");
  const [crackLoading, setCrackLoading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [settingsRes, statusRes, attemptsRes] = await Promise.all([
        axios.get(`${API}/settings`),
        axios.get(`${API}/status`),
        axios.get(`${API}/attempts`)
      ]);
      setSettings(settingsRes.data);
      setTempSettings({
        bot_token: settingsRes.data.bot_token || "",
        chat_id: settingsRes.data.chat_id || ""
      });
      setStatus(statusRes.data);
      setAttempts(attemptsRes.data);
    } catch (e) {
      console.error("Error fetching data:", e);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const saveSettings = async () => {
    setLoading(true);
    try {
      await axios.post(`${API}/settings`, tempSettings);
      setEditMode(false);
      await fetchData();
    } catch (e) {
      console.error("Error saving settings:", e);
      alert("Failed to save settings");
    }
    setLoading(false);
  };

  const toggleBot = async () => {
    setLoading(true);
    try {
      if (status.is_running) {
        await axios.post(`${API}/bot/stop`);
      } else {
        await axios.post(`${API}/bot/start`);
      }
      await fetchData();
    } catch (e) {
      console.error("Error toggling bot:", e);
      alert(e.response?.data?.detail || "Failed to toggle bot");
    }
    setLoading(false);
  };

  const deleteAttempt = async (id) => {
    try {
      await axios.delete(`${API}/attempts/${id}`);
      await fetchData();
    } catch (e) {
      console.error("Error deleting:", e);
    }
  };

  const handleManualCrack = async () => {
    if (!selectedFile || !crackName) {
      alert("Select PDF file and enter name!");
      return;
    }
    if (crackName.length < 4) {
      alert("Name must be at least 4 characters!");
      return;
    }
    
    setCrackLoading(true);
    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("name", crackName);
    
    try {
      await axios.post(`${API}/crack`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      setSelectedFile(null);
      setCrackName("");
      await fetchData();
    } catch (e) {
      console.error("Error starting crack:", e);
      alert(e.response?.data?.detail || "Failed to start crack");
    }
    setCrackLoading(false);
  };

  const maskToken = (token) => {
    if (!token) return "Not Set";
    return token.substring(0, 10) + "..." + token.substring(token.length - 5);
  };

  return (
    <div className="min-h-screen bg-[#050505] text-[#00ff41] font-mono">
      {/* Scanline overlay */}
      <div className="scanline-overlay"></div>
      
      {/* Header */}
      <header className="border-b border-[#333] p-4">
        <div className="max-w-7xl mx-auto flex items-center gap-3">
          <Terminal className="w-6 h-6" />
          <h1 className="text-xl font-bold tracking-wider uppercase" data-testid="app-title">
            PDF PASSWORD CRACKER
          </h1>
          <span className="ml-auto flex items-center gap-2 text-xs">
            <span className={`w-2 h-2 rounded-full ${status.is_running ? 'bg-[#00ff41]' : 'bg-red-500'}`}></span>
            {status.is_running ? "BOT ONLINE" : "BOT OFFLINE"}
          </span>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="border-b border-[#333]">
        <div className="max-w-7xl mx-auto flex">
          {[
            { id: "status", label: "STATUS", icon: Activity },
            { id: "settings", label: "SETTINGS", icon: Settings },
            { id: "crack", label: "MANUAL CRACK", icon: Lock },
            { id: "history", label: "HISTORY", icon: FileText }
          ].map(tab => (
            <button
              key={tab.id}
              data-testid={`tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-6 py-3 text-xs uppercase tracking-wider border-r border-[#333] transition-all
                ${activeTab === tab.id 
                  ? 'bg-[#00ff41] text-black' 
                  : 'hover:bg-[#1a1a1a]'}`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto p-6">
        {/* Status Tab */}
        {activeTab === "status" && (
          <div className="space-y-6" data-testid="status-panel">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Bot Status Card */}
              <div className="border border-[#333] bg-[#0a0a0a]">
                <div className="border-b border-[#333] p-3 text-xs tracking-widest text-[#525252] uppercase">
                  Bot Status
                </div>
                <div className="p-6 flex flex-col items-center">
                  <div className={`w-16 h-16 rounded-full border-2 flex items-center justify-center mb-4
                    ${status.is_running ? 'border-[#00ff41] text-[#00ff41]' : 'border-red-500 text-red-500'}`}>
                    <Shield className="w-8 h-8" />
                  </div>
                  <p className="text-lg font-bold">{status.is_running ? "ACTIVE" : "INACTIVE"}</p>
                  <button
                    data-testid="toggle-bot-btn"
                    onClick={toggleBot}
                    disabled={loading || !status.bot_token_set}
                    className={`mt-4 flex items-center gap-2 px-4 py-2 text-xs uppercase tracking-wider border transition-all
                      ${status.is_running 
                        ? 'border-red-500 text-red-500 hover:bg-red-500 hover:text-white' 
                        : 'border-[#00ff41] text-[#00ff41] hover:bg-[#00ff41] hover:text-black'}
                      disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    {status.is_running ? <Square className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                    {status.is_running ? "STOP BOT" : "START BOT"}
                  </button>
                </div>
              </div>

              {/* Token Status Card */}
              <div className="border border-[#333] bg-[#0a0a0a]">
                <div className="border-b border-[#333] p-3 text-xs tracking-widest text-[#525252] uppercase">
                  Bot Token
                </div>
                <div className="p-6">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`w-2 h-2 rounded-full ${status.bot_token_set ? 'bg-[#00ff41]' : 'bg-red-500'}`}></span>
                    <span className="text-xs uppercase">{status.bot_token_set ? "Configured" : "Not Set"}</span>
                  </div>
                  <p className="text-xs text-[#525252] break-all font-mono">
                    {maskToken(settings.bot_token)}
                  </p>
                </div>
              </div>

              {/* Chat ID Card */}
              <div className="border border-[#333] bg-[#0a0a0a]">
                <div className="border-b border-[#333] p-3 text-xs tracking-widest text-[#525252] uppercase">
                  Chat ID
                </div>
                <div className="p-6">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`w-2 h-2 rounded-full ${status.chat_id_set ? 'bg-[#00ff41]' : 'bg-[#facc15]'}`}></span>
                    <span className="text-xs uppercase">{status.chat_id_set ? "Configured" : "Optional"}</span>
                  </div>
                  <p className="text-lg font-bold font-mono">
                    {settings.chat_id || "Not Set"}
                  </p>
                </div>
              </div>
            </div>

            {/* Recent Activity */}
            <div className="border border-[#333] bg-[#0a0a0a]">
              <div className="border-b border-[#333] p-3 text-xs tracking-widest text-[#525252] uppercase flex items-center justify-between">
                <span>Recent Activity</span>
                <button onClick={fetchData} className="hover:text-[#00ff41]">
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
              <div className="p-4">
                {attempts.slice(0, 5).map(attempt => (
                  <div key={attempt.id} className="flex items-center justify-between py-2 border-b border-[#1a1a1a] last:border-0">
                    <div className="flex items-center gap-3">
                      <span className={`w-2 h-2 rounded-full ${
                        attempt.status === 'success' ? 'bg-[#00ff41]' :
                        attempt.status === 'failed' ? 'bg-red-500' :
                        'bg-[#facc15] animate-pulse'
                      }`}></span>
                      <span className="text-sm truncate max-w-[200px]">{attempt.filename}</span>
                    </div>
                    <span className="text-xs text-[#525252] uppercase">{attempt.status}</span>
                  </div>
                ))}
                {attempts.length === 0 && (
                  <p className="text-center text-[#525252] py-4">No activity yet</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Settings Tab */}
        {activeTab === "settings" && (
          <div className="max-w-xl" data-testid="settings-panel">
            <div className="border border-[#333] bg-[#0a0a0a]">
              <div className="border-b border-[#333] p-3 text-xs tracking-widest text-[#525252] uppercase flex items-center justify-between">
                <span>Bot Configuration</span>
                {!editMode && (
                  <button
                    data-testid="edit-settings-btn"
                    onClick={() => setEditMode(true)}
                    className="text-[#00ff41] hover:underline text-xs"
                  >
                    EDIT
                  </button>
                )}
              </div>
              <div className="p-6 space-y-6">
                {/* Bot Token */}
                <div>
                  <label className="block text-xs uppercase tracking-wider mb-2 text-[#525252]">
                    Telegram Bot Token
                  </label>
                  {editMode ? (
                    <input
                      data-testid="bot-token-input"
                      type="text"
                      value={tempSettings.bot_token}
                      onChange={(e) => setTempSettings({...tempSettings, bot_token: e.target.value})}
                      placeholder="Enter bot token from @BotFather"
                      className="w-full bg-black border-b border-[#333] focus:border-[#00ff41] focus:outline-none px-0 py-2 text-sm font-mono placeholder:text-[#525252]/50"
                    />
                  ) : (
                    <p className="text-sm font-mono break-all">{maskToken(settings.bot_token)}</p>
                  )}
                </div>

                {/* Chat ID */}
                <div>
                  <label className="block text-xs uppercase tracking-wider mb-2 text-[#525252]">
                    Default Chat ID (Optional)
                  </label>
                  {editMode ? (
                    <input
                      data-testid="chat-id-input"
                      type="text"
                      value={tempSettings.chat_id}
                      onChange={(e) => setTempSettings({...tempSettings, chat_id: e.target.value})}
                      placeholder="Enter chat ID for notifications"
                      className="w-full bg-black border-b border-[#333] focus:border-[#00ff41] focus:outline-none px-0 py-2 text-sm font-mono placeholder:text-[#525252]/50"
                    />
                  ) : (
                    <p className="text-sm font-mono">{settings.chat_id || "Not Set"}</p>
                  )}
                </div>

                {/* Buttons */}
                {editMode && (
                  <div className="flex gap-3 pt-4">
                    <button
                      data-testid="save-settings-btn"
                      onClick={saveSettings}
                      disabled={loading}
                      className="flex-1 border border-[#00ff41] text-[#00ff41] hover:bg-[#00ff41] hover:text-black px-4 py-2 text-xs uppercase tracking-wider transition-all disabled:opacity-50"
                    >
                      {loading ? "SAVING..." : "SAVE"}
                    </button>
                    <button
                      data-testid="cancel-edit-btn"
                      onClick={() => {
                        setEditMode(false);
                        setTempSettings({
                          bot_token: settings.bot_token || "",
                          chat_id: settings.chat_id || ""
                        });
                      }}
                      className="flex-1 border border-[#525252] text-[#525252] hover:border-[#00ff41] hover:text-[#00ff41] px-4 py-2 text-xs uppercase tracking-wider transition-all"
                    >
                      CANCEL
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Instructions */}
            <div className="border border-[#333] bg-[#0a0a0a] mt-4">
              <div className="border-b border-[#333] p-3 text-xs tracking-widest text-[#525252] uppercase">
                How to Get Bot Token
              </div>
              <div className="p-6 text-xs text-[#525252] space-y-2">
                <p>1. Open Telegram and search for @BotFather</p>
                <p>2. Send /newbot command</p>
                <p>3. Follow instructions to create bot</p>
                <p>4. Copy the token and paste above</p>
              </div>
            </div>
          </div>
        )}

        {/* Manual Crack Tab */}
        {activeTab === "crack" && (
          <div className="max-w-xl" data-testid="crack-panel">
            <div className="border border-[#333] bg-[#0a0a0a]">
              <div className="border-b border-[#333] p-3 text-xs tracking-widest text-[#525252] uppercase">
                Manual PDF Crack
              </div>
              <div className="p-6 space-y-6">
                {/* File Upload */}
                <div>
                  <label className="block text-xs uppercase tracking-wider mb-2 text-[#525252]">
                    Select PDF File
                  </label>
                  <label 
                    data-testid="file-upload-label"
                    className="flex items-center justify-center gap-2 border border-dashed border-[#333] hover:border-[#00ff41] p-8 cursor-pointer transition-all"
                  >
                    <Upload className="w-6 h-6" />
                    <span className="text-sm">{selectedFile ? selectedFile.name : "Click to upload PDF"}</span>
                    <input
                      data-testid="file-upload-input"
                      type="file"
                      accept=".pdf"
                      onChange={(e) => setSelectedFile(e.target.files[0])}
                      className="hidden"
                    />
                  </label>
                </div>

                {/* Name Input */}
                <div>
                  <label className="block text-xs uppercase tracking-wider mb-2 text-[#525252]">
                    Name to Try (min 4 characters)
                  </label>
                  <input
                    data-testid="crack-name-input"
                    type="text"
                    value={crackName}
                    onChange={(e) => setCrackName(e.target.value)}
                    placeholder="e.g., Rohit (will try ROHI + years)"
                    className="w-full bg-black border-b border-[#333] focus:border-[#00ff41] focus:outline-none px-0 py-2 text-sm font-mono placeholder:text-[#525252]/50"
                  />
                  {crackName.length >= 4 && (
                    <p className="text-xs text-[#525252] mt-2">
                      Will try: {crackName.slice(0, 4).toUpperCase()}1900, {crackName.slice(0, 4).toUpperCase()}1901, ... {crackName.slice(0, 4).toUpperCase()}2026
                    </p>
                  )}
                </div>

                {/* Start Button */}
                <button
                  data-testid="start-crack-btn"
                  onClick={handleManualCrack}
                  disabled={crackLoading || !selectedFile || crackName.length < 4}
                  className="w-full flex items-center justify-center gap-2 border border-[#00ff41] text-[#00ff41] hover:bg-[#00ff41] hover:text-black px-4 py-3 text-xs uppercase tracking-wider transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Lock className="w-4 h-4" />
                  {crackLoading ? "CRACKING..." : "START CRACK"}
                </button>
              </div>
            </div>

            {/* Info Box */}
            <div className="border border-[#333] bg-[#0a0a0a] mt-4">
              <div className="border-b border-[#333] p-3 text-xs tracking-widest text-[#525252] uppercase">
                Password Format
              </div>
              <div className="p-6 text-xs text-[#525252] space-y-2">
                <p>Format: NAME (first 4 letters CAPS) + YEAR</p>
                <p>Example: Rohit → ROHI2006</p>
                <p>Tries all years from 1900 to 2026 (127 combinations)</p>
              </div>
            </div>
          </div>
        )}

        {/* History Tab */}
        {activeTab === "history" && (
          <div data-testid="history-panel">
            <div className="border border-[#333] bg-[#0a0a0a]">
              <div className="border-b border-[#333] p-3 text-xs tracking-widest text-[#525252] uppercase flex items-center justify-between">
                <span>Crack History</span>
                <button onClick={fetchData} className="hover:text-[#00ff41]">
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
              <div className="divide-y divide-[#1a1a1a]">
                {attempts.map(attempt => (
                  <div key={attempt.id} className="p-4 hover:bg-[#1a1a1a] transition-all">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`px-2 py-0.5 text-xs uppercase border ${
                            attempt.status === 'success' ? 'border-[#00ff41] text-[#00ff41]' :
                            attempt.status === 'failed' ? 'border-red-500 text-red-500' :
                            'border-[#facc15] text-[#facc15]'
                          }`}>
                            {attempt.status}
                          </span>
                          <span className="text-xs text-[#525252]">
                            {new Date(attempt.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-sm mb-1 truncate">{attempt.filename}</p>
                        <p className="text-xs text-[#525252]">
                          Name: {attempt.name_used} | Attempts: {attempt.attempts_tried}/{attempt.total_attempts}
                        </p>
                        {attempt.password_found && (
                          <p className="text-sm mt-2 text-[#00ff41] font-bold">
                            Password: {attempt.password_found}
                          </p>
                        )}
                      </div>
                      <button
                        data-testid={`delete-attempt-${attempt.id}`}
                        onClick={() => deleteAttempt(attempt.id)}
                        className="text-[#525252] hover:text-red-500 p-2"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
                {attempts.length === 0 && (
                  <div className="p-8 text-center text-[#525252]">
                    <Lock className="w-12 h-12 mx-auto mb-4 opacity-50" />
                    <p>No crack attempts yet</p>
                    <p className="text-xs mt-2">Use the bot or manual crack to start</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-[#333] p-4 mt-8">
        <div className="max-w-7xl mx-auto text-center text-xs text-[#525252]">
          PDF PASSWORD CRACKER | Format: NAME (4 letters) + YEAR (1900-2026)
        </div>
      </footer>
    </div>
  );
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
