import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send, Bot, Radio, MessageSquare, CheckCircle, XCircle, Info } from "lucide-react";

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return ok ? (
    <Badge className="bg-green-100 text-green-700 gap-1 font-normal">
      <CheckCircle className="w-3 h-3" /> {label}
    </Badge>
  ) : (
    <Badge className="bg-red-100 text-red-700 gap-1 font-normal">
      <XCircle className="w-3 h-3" /> {label}
    </Badge>
  );
}

export default function TelegramBot() {
  const qc = useQueryClient();
  const [testMsg, setTestMsg] = useState("");
  const [testResult, setTestResult] = useState<{ text: string; response: string } | null>(null);

  const { data: status, isLoading } = useQuery({
    queryKey: ["telegram-status"],
    queryFn: () => api.telegramStatus(),
    refetchInterval: 15000,
  });

  const { data: messages = [] } = useQuery({
    queryKey: ["telegram-messages"],
    queryFn: () => api.telegramMessages(),
    refetchInterval: 8000,
  });

  const testMutation = useMutation({
    mutationFn: (text: string) => api.telegramTest(text),
    onSuccess: (data) => {
      setTestResult(data as any);
      qc.invalidateQueries({ queryKey: ["telegram-messages"] });
    },
  });

  const handleTest = () => {
    if (!testMsg.trim()) return;
    testMutation.mutate(testMsg.trim());
    setTestMsg("");
  };

  const botInfo    = (status as any)?.botInfo;
  const configured = (status as any)?.configured;
  const mode       = (status as any)?.mode ?? "polling";

  if (isLoading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading…</div>;
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Bot className="w-7 h-7 text-blue-500" /> Telegram Bot
        </h1>
        <p className="text-gray-500 mt-1 text-sm">
          Real-time NSE market data via Telegram with full NLP support.
        </p>
      </div>

      {/* Status Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-gray-400 mb-1">Bot</p>
            <StatusBadge ok={!!configured} label={configured ? "Token Active" : "Not Configured"} />
            {botInfo?.username && (
              <p className="text-sm text-gray-700 mt-2 font-semibold">@{botInfo.username}</p>
            )}
            {botInfo?.botName && (
              <p className="text-xs text-gray-400">{botInfo.botName}</p>
            )}
            {botInfo?.error && <p className="text-xs text-red-500 mt-1">{botInfo.error}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-gray-400 mb-1">Connection Mode</p>
            {configured ? (
              <Badge className="bg-blue-100 text-blue-700 gap-1 font-normal">
                <Radio className="w-3 h-3" /> Long Polling
              </Badge>
            ) : (
              <StatusBadge ok={false} label="Inactive" />
            )}
            <p className="text-xs text-gray-400 mt-2">No webhook required</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-gray-400 mb-1">Messages Handled</p>
            <p className="text-2xl font-bold text-gray-900">{(status as any)?.totalMessages ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Setup Guide */}
      {!configured && (
        <Card className="border-blue-200 bg-blue-50">
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-blue-800 flex items-center gap-2">
              <Info className="w-4 h-4" /> Setup Instructions
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-blue-900">
            <ol className="list-decimal list-inside space-y-2">
              <li>Open Telegram and message <strong>@BotFather</strong></li>
              <li>Send <code className="bg-blue-100 px-1 rounded">/newbot</code> and follow the prompts</li>
              <li>Copy the bot token BotFather gives you</li>
              <li>
                In Replit, go to <strong>Secrets</strong> and add:
                <br />
                <code className="bg-blue-100 px-1 rounded text-xs">TELEGRAM_BOT_TOKEN</code> = your token
              </li>
              <li>Restart the <strong>Python Backend</strong> workflow — polling starts automatically</li>
            </ol>
          </CardContent>
        </Card>
      )}

      {/* Live polling info */}
      {configured && (
        <Card className="border-green-200 bg-green-50">
          <CardContent className="pt-4 flex items-start gap-3">
            <Radio className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0 animate-pulse" />
            <div>
              <p className="text-sm font-medium text-green-800">Polling Active</p>
              <p className="text-xs text-green-700 mt-0.5">
                The backend is continuously polling Telegram for new messages. No webhook or extra setup needed — just open Telegram, search for <strong>@{botInfo?.username ?? "your bot"}</strong> and start chatting.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Test Panel */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <MessageSquare className="w-4 h-4 text-green-500" /> Test Bot (No Telegram needed)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-gray-400">Try any command or plain-English query below — the response is what the bot would send in Telegram.</p>
          <div className="flex gap-2">
            <Input
              placeholder="/analyze RELIANCE, /sectors, which sectors are up today?"
              value={testMsg}
              onChange={e => setTestMsg(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleTest()}
            />
            <Button
              onClick={handleTest}
              disabled={!testMsg.trim() || testMutation.isPending}
              size="sm"
            >
              <Send className="w-4 h-4" />
            </Button>
          </div>
          {testMutation.isPending && (
            <p className="text-xs text-gray-400">Processing…</p>
          )}
          {testResult && (
            <div className="space-y-2">
              <div className="bg-gray-50 border rounded px-3 py-2 text-sm text-gray-600">
                <span className="text-xs text-gray-400 block mb-0.5">You sent:</span>
                {testResult.text}
              </div>
              <div className="bg-blue-50 border border-blue-100 rounded px-3 py-2 text-sm text-gray-800 whitespace-pre-wrap">
                <span className="text-xs text-blue-400 block mb-0.5">Bot replied:</span>
                {testResult.response}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Commands Reference */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Supported Commands</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {((status as any)?.commands ?? []).map((cmd: string) => {
              const [c, ...rest] = cmd.split(" — ");
              return (
                <div key={cmd} className="flex items-start gap-2 text-sm">
                  <code className="bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded text-xs font-mono flex-shrink-0">{c}</code>
                  <span className="text-gray-500 text-xs">{rest.join(" — ")}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-3 p-3 bg-gray-50 rounded text-xs text-gray-500">
            <strong>Natural language works too:</strong> "analyze RELIANCE", "which sectors are up?",
            "show bullish patterns", "where to invest today?" — just type naturally.
          </div>
        </CardContent>
      </Card>

      {/* Message Log */}
      {messages.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Recent Messages</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 max-h-72 overflow-y-auto">
              {messages.slice(0, 20).map((m: any, i: number) => (
                <div key={i} className="border-b border-gray-50 pb-2 last:border-0">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-gray-600">{m.from}</span>
                    <span className="text-xs text-gray-400">{new Date(m.timestamp).toLocaleTimeString()}</span>
                  </div>
                  <p className="text-xs text-gray-500">→ {m.text}</p>
                  <p className="text-xs text-blue-600 mt-0.5 line-clamp-2">← {m.response?.split("\n")[0]}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
