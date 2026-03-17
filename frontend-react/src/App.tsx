import React, { useState, useEffect, useRef } from 'react';
import { Send, TrendingUp, AlertTriangle, MessageSquare, Briefcase, Activity } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function MessageBubble({ msg }: { msg: { role: string; content: string } }) {
  const content = msg.content || '';
  const thinkMatch = content.match(/<think>([\s\S]*?)(?:<\/think>|$)/);

  let thinkContent = null;
  let actualContent = content;
  let isThinking = false;

  if (thinkMatch) {
    isThinking = !content.includes('</think>');
    thinkContent = thinkMatch[1].trim();
    actualContent = content.replace(/<think>[\s\S]*?(?:<\/think>|$)/g, '').trim();
  }

  const [isExpanded, setIsExpanded] = useState(() => {
    if (!thinkMatch) return false;
    return isThinking;
  });

  // Auto-collapse when thinking finishes
  const wasThinking = useRef(isThinking);
  useEffect(() => {
    if (wasThinking.current && !isThinking) {
      setIsExpanded(false);
    }
    wasThinking.current = isThinking;
  }, [isThinking]);

  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-3xl rounded-2xl p-4 bg-blue-600 text-white shadow-sm">
          <div className="whitespace-pre-wrap font-medium">{msg.content}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-3xl min-w-[50%] rounded-2xl p-5 bg-gray-800 text-gray-200 shadow-sm border border-gray-700 flex flex-col gap-4">
        {thinkContent !== null && (
          <div className="bg-gray-900/50 rounded-lg border border-gray-700 overflow-hidden">
            <button 
              onClick={() => setIsExpanded(!isExpanded)}
              className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-800 transition-colors border-b border-transparent hover:border-gray-700"
            >
              <div className="flex items-center gap-2 text-indigo-400 text-sm font-semibold">
                <Activity size={16} className={isThinking ? 'animate-pulse text-indigo-500' : ''} />
                {isThinking ? 'ARIA is thinking...' : 'Thought Process'}
              </div>
              <span className="text-gray-500 text-xs font-medium uppercase tracking-wider">
                {isExpanded ? 'Hide' : 'Show'}
              </span>
            </button>
            {isExpanded && (
              <div className={`px-4 pb-4 pt-2 text-gray-400 text-sm whitespace-pre-wrap border-t border-gray-700/50 ${isThinking ? 'animate-pulse' : ''}`}>
                {thinkContent || 'Starting thought process...'}
              </div>
            )}
          </div>
        )}
        
        {actualContent && (
          <div className="prose prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-700">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {actualContent}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

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
            const lastMsg = newMsgs[newMsgs.length - 1];
            newMsgs[newMsgs.length - 1] = {
              ...lastMsg,
              content: lastMsg.content + data.content
            };
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
                <MessageBubble key={idx} msg={msg} />
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
