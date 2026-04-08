'use client';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { WhatsAppStatus, BotMessage } from '@/types';
import { MessageSquare, QrCode, Power, Send, Clock, CheckCircle, XCircle } from 'lucide-react';
import { clsx } from 'clsx';

export default function BotPage() {
  const [testMessage, setTestMessage] = useState('');
  const [testResponse, setTestResponse] = useState('');
  const queryClient = useQueryClient();

  const { data: status, isLoading } = useQuery({
    queryKey: ['bot-status'],
    queryFn: () => api.whatsapp.getStatus().then(r => r.data as WhatsAppStatus),
    refetchInterval: 5000,
  });

  const { data: messages = [] } = useQuery({
    queryKey: ['bot-messages'],
    queryFn: () => api.whatsapp.getMessages().then(r => r.data as BotMessage[]),
    refetchInterval: 10000,
  });

  const qrMutation = useMutation({
    mutationFn: () => api.whatsapp.generateQr(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['bot-status'] }),
  });

  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) => api.whatsapp.updateStatus(enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['bot-status'] }),
  });

  const testMutation = useMutation({
    mutationFn: (msg: string) => api.whatsapp.sendMessage({
      from: 'test@test.com',
      body: msg,
      timestamp: new Date().toISOString(),
    }),
    onSuccess: (data) => {
      setTestResponse(data.data?.message || '');
    },
  });

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-white">WhatsApp Bot</h1>
        <p className="text-slate-500 text-sm mt-1">Configure and test the NSE market analysis WhatsApp bot</p>
      </div>

      {/* Status Card */}
      <div className="card border border-white/[0.08]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={clsx(
              'w-10 h-10 rounded-full flex items-center justify-center',
              status?.isConnected ? 'bg-green-500/20' : 'bg-slate-500/20'
            )}>
              <MessageSquare className={clsx('w-5 h-5', status?.isConnected ? 'text-green-400' : 'text-slate-400')} />
            </div>
            <div>
              <div className="font-semibold text-white">Bot Status</div>
              <div className="flex items-center gap-2 mt-0.5">
                {status?.isConnected ? (
                  <CheckCircle className="w-3.5 h-3.5 text-green-400" />
                ) : (
                  <XCircle className="w-3.5 h-3.5 text-red-400" />
                )}
                <span className={clsx('text-sm', status?.isConnected ? 'text-green-400' : 'text-slate-400')}>
                  {status?.isConnected ? 'Connected' : 'Disconnected'}
                </span>
                {status?.botEnabled !== undefined && (
                  <>
                    <span className="text-slate-600">•</span>
                    <span className={clsx('text-sm', status.botEnabled ? 'text-blue-400' : 'text-slate-500')}>
                      Bot {status.botEnabled ? 'Active' : 'Paused'}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => toggleMutation.mutate(!status?.botEnabled)}
              className={clsx(
                'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                status?.botEnabled
                  ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20'
                  : 'bg-green-500/10 text-green-400 hover:bg-green-500/20 border border-green-500/20'
              )}
            >
              <Power className="w-4 h-4" />
              {status?.botEnabled ? 'Pause Bot' : 'Enable Bot'}
            </button>
            <button
              onClick={() => qrMutation.mutate()}
              className="flex items-center gap-2 px-3 py-2 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded-lg text-sm font-medium border border-blue-500/20 transition-colors"
            >
              <QrCode className="w-4 h-4" />
              Connect WhatsApp
            </button>
          </div>
        </div>

        {status && (
          <div className="mt-4 pt-4 border-t border-white/[0.06] grid grid-cols-2 md:grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-slate-500">Messages Handled</div>
              <div className="text-lg font-bold text-white mt-0.5">{status.messageCount}</div>
            </div>
            {status.lastActivity && (
              <div>
                <div className="text-xs text-slate-500">Last Activity</div>
                <div className="text-sm text-slate-300 mt-0.5">
                  {new Date(status.lastActivity).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* QR Code */}
      {status?.qrCode && (
        <div className="card border border-yellow-500/20 bg-yellow-500/5">
          <div className="flex items-start gap-3">
            <QrCode className="w-5 h-5 text-yellow-400 mt-0.5" />
            <div>
              <div className="font-medium text-yellow-400">QR Code Generated</div>
              <div className="text-sm text-slate-400 mt-1">
                In production, a QR code will appear here. Scan it with WhatsApp to connect the bot.
                whatsapp-web.js handles the session automatically.
              </div>
              <div className="mt-2 font-mono text-xs text-slate-500 break-all">{status.qrCode}</div>
            </div>
          </div>
        </div>
      )}

      {/* Bot Commands */}
      <div className="card">
        <h2 className="font-semibold text-white mb-4">Bot Commands</h2>
        <div className="grid md:grid-cols-2 gap-2">
          {status?.capabilities?.map((cap, i) => (
            <div key={i} className="flex items-start gap-2 p-2 rounded bg-white/[0.02] text-sm">
              <span className="text-blue-400 mt-0.5">•</span>
              <span className="text-slate-300">{cap}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Test Bot */}
      <div className="card">
        <h2 className="font-semibold text-white mb-4">Test Bot</h2>
        <div className="flex gap-3">
          <input
            type="text"
            value={testMessage}
            onChange={e => setTestMessage(e.target.value)}
            placeholder="Type a command (e.g. RELIANCE, /sectors, /rotation)"
            className="flex-1 px-3 py-2 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white placeholder-slate-500 text-sm focus:outline-none focus:border-blue-500/50"
            onKeyDown={e => e.key === 'Enter' && testMutation.mutate(testMessage)}
          />
          <button
            onClick={() => testMutation.mutate(testMessage)}
            disabled={!testMessage || testMutation.isPending}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Send className="w-4 h-4" />
            Test
          </button>
        </div>

        <div className="flex flex-wrap gap-2 mt-3">
          {['/help', '/sectors', '/rotation', '/patterns', 'RELIANCE', 'TCS', '/scanners'].map(cmd => (
            <button
              key={cmd}
              onClick={() => { setTestMessage(cmd); testMutation.mutate(cmd); }}
              className="text-xs px-2.5 py-1 rounded bg-white/[0.04] text-slate-400 hover:text-white hover:bg-white/[0.08] transition-colors border border-white/[0.06] font-mono"
            >
              {cmd}
            </button>
          ))}
        </div>

        {testResponse && (
          <div className="mt-4 p-4 rounded-lg bg-green-500/5 border border-green-500/20">
            <div className="text-xs text-green-400 font-medium mb-2">Bot Response:</div>
            <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans leading-relaxed">{testResponse}</pre>
          </div>
        )}
      </div>

      {/* Message Log */}
      {messages.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-white mb-4">Recent Messages</h2>
          <div className="space-y-3 max-h-80 overflow-y-auto">
            {[...messages].reverse().slice(0, 20).map((msg, i) => (
              <div key={i} className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-slate-500 font-mono">{msg.message?.from}</span>
                  <span className="text-xs text-slate-600">
                    <Clock className="w-3 h-3 inline mr-1" />
                    {new Date(msg.timestamp).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })}
                  </span>
                </div>
                <div className="text-sm text-blue-300 font-medium mb-1">Q: {msg.message?.body}</div>
                <div className="text-xs text-slate-400 truncate">{msg.response?.slice(0, 100)}...</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Setup Instructions */}
      <div className="card border border-slate-700">
        <h2 className="font-semibold text-white mb-3">Production Setup</h2>
        <div className="space-y-2 text-sm text-slate-400">
          <div className="flex gap-2"><span className="text-blue-400 font-bold">1.</span> Deploy the NestJS backend on a server with Chrome/Puppeteer support</div>
          <div className="flex gap-2"><span className="text-blue-400 font-bold">2.</span> The bot uses <code className="text-xs bg-white/[0.06] px-1 rounded">whatsapp-web.js</code> which requires a headless browser</div>
          <div className="flex gap-2"><span className="text-blue-400 font-bold">3.</span> On first start, scan the QR code with your WhatsApp to link the session</div>
          <div className="flex gap-2"><span className="text-blue-400 font-bold">4.</span> Session is saved automatically — reconnects without QR after restart</div>
          <div className="flex gap-2"><span className="text-blue-400 font-bold">5.</span> Data is refreshed from NSE/Yahoo Finance at market close (5 PM IST)</div>
          <div className="flex gap-2"><span className="text-blue-400 font-bold">6.</span> Set <code className="text-xs bg-white/[0.06] px-1 rounded">NEXT_PUBLIC_API_URL</code> in your Next.js env to point to the NestJS backend</div>
        </div>
      </div>
    </div>
  );
}
