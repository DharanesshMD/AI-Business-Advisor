import React, { useState, useEffect, useRef } from 'react';
import { Send, TrendingUp, AlertTriangle, MessageSquare, Briefcase, Activity } from 'lucide-react';

export default function App() {
  const [messages, setMessages] = useState<{role: string, content: string}[]>([]);
  const [input, setInput] = useState('');
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [portfolioData, setPortfolioData] = useState<any>(null);
  const [activeTab, setActiveTab] = useState('chat');
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Initialize Chat WebSocket
    const chatWs = new WebSocket('ws://localhost:8000/ws/chat');
    
    chatWs.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'token') {
        setMessages(prev => {
          const newMsgs = [...prev];
          if (newMsgs.length > 0 && newMsgs[newMsgs.length - 1].role === 'assistant') {
            newMsgs[newMsgs.length - 1].content += data.content;
          } else {
            newMsgs.push({ role: 'assistant', content: data.content });
          }
          return newMsgs;
        });
      } else if (data.type === 'system') {
        setMessages(prev => [...prev, { role: 'assistant', content: data.content }]);
      }
    };
    setWs(chatWs);

    // Initialize Portfolio WebSocket
    const portWs = new WebSocket('ws://localhost:8000/ws/portfolio');
    portWs.onopen = () => {
      // Send a dummy portfolio to start monitoring
      portWs.send(JSON.stringify({
        action: 'monitor',
        holdings: [
          { symbol: "AAPL", quantity: 10, purchase_price: 150 },
          { symbol: "MSFT", quantity: 5, purchase_price: 300 }
        ],
        constraints: { max_var_95: 0.05 }
      }));
    };

    portWs.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'monitoring_update' || data.type === 'risk_alert') {
        setPortfolioData(data.data || data); // handle both formats
      }
    };

    return () => {
      chatWs.close();
      portWs.close();
    };
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !ws) return;

    setMessages(prev => [...prev, { role: 'user', content: input }]);
    ws.send(JSON.stringify({
      type: 'message',
      content: input,
      location: 'United States',
      search_provider: 'auto'
    }));
    setInput('');
  };

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100 font-sans">
      {/* Sidebar */}
      <div className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Activity className="text-blue-500" />
            ARIA OS
          </h1>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <button 
            onClick={() => setActiveTab('chat')}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${activeTab === 'chat' ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
          >
            <MessageSquare size={20} /> Advisor Chat
          </button>
          <button 
            onClick={() => setActiveTab('portfolio')}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${activeTab === 'portfolio' ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
          >
            <Briefcase size={20} /> Portfolio Risk
          </button>
        </nav>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {activeTab === 'chat' ? (
          <>
            {/* Chat Area */}
            <div className="flex-1 p-6 overflow-y-auto space-y-6">
              {messages.map((msg, idx) => (
                <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-3xl rounded-2xl p-4 ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-200'}`}>
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            {/* Input Area */}
            <div className="p-4 border-t border-gray-800 bg-gray-900">
              <form onSubmit={sendMessage} className="max-w-4xl mx-auto flex gap-4">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask ARIA about a company, regulation, or market trend..."
                  className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button type="submit" className="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded-lg font-medium flex items-center gap-2 transition-colors">
                  <Send size={18} />
                  Send
                </button>
              </form>
            </div>
          </>
        ) : (
          /* Portfolio Dashboard */
          <div className="flex-1 p-8 overflow-y-auto">
            <h2 className="text-2xl font-bold mb-6">Live Risk Dashboard</h2>
            
            {portfolioData ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Key Metrics */}
                <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                  <h3 className="text-gray-400 font-medium mb-2 flex items-center gap-2"><AlertTriangle size={18}/> Value at Risk (95%)</h3>
                  <div className="text-4xl font-bold text-red-400">
                    {(portfolioData.metrics?.var_metrics?.var_95 * 100)?.toFixed(2)}%
                  </div>
                </div>
                <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                  <h3 className="text-gray-400 font-medium mb-2 flex items-center gap-2"><TrendingUp size={18}/> Sharpe Ratio</h3>
                  <div className="text-4xl font-bold text-green-400">
                    {portfolioData.metrics?.perf_metrics?.sharpe_ratio?.toFixed(2)}
                  </div>
                </div>
                <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                  <h3 className="text-gray-400 font-medium mb-2">Status</h3>
                  <div className={`text-4xl font-bold ${portfolioData.status === 'Warning' ? 'text-yellow-500' : 'text-green-500'}`}>
                    {portfolioData.status}
                  </div>
                </div>

                {/* Alerts */}
                {portfolioData.alerts?.length > 0 && (
                  <div className="col-span-full bg-yellow-900/20 border border-yellow-700/50 rounded-xl p-6 mt-6">
                    <h3 className="text-yellow-500 font-medium mb-4 flex items-center gap-2"><AlertTriangle size={18}/> Active Alerts</h3>
                    <ul className="space-y-3">
                      {portfolioData.alerts.map((alert: any, i: number) => (
                        <li key={i} className="flex flex-col gap-1">
                          <span className="font-medium text-yellow-400">{alert.message}</span>
                          <span className="text-sm text-gray-400">Recommendation: {alert.rec}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-64 text-gray-500">
                Connecting to risk engine...
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
