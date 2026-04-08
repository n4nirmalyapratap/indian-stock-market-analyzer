import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send, Bot, Webhook, MessageSquare, CheckCircle, XCircle, Info } from "lucide-react";

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
  const [webhookUrl, setWebhookUrl] = useState("");
  const [testResult, setTestResult] = useState<{ text: string; response: string } | null>(null);
  const [webhookResult, setWebhookResult] = useState<{ success: boolean; description: string } | null>(null);

  const { data: status, isLoading } = useQuery({
    queryKey: ["telegram-status"],
    queryFn: () => api.telegramStatus(),
    refetchInterval: 15000,
  });

  const { data: messages = [] } = useQuery({
    queryKey: ["telegram-messages"],
    queryFn: () => api.telegramMessages(),
    refetchInterval: 10000,
  });

  const testMutation = useMutation({
    mutationFn: (text: string) => api.telegramTest(text),
    onSuccess: (data) => {
      setTestResult(data as any);
      qc.invalidateQueries({ queryKey: ["telegram-messages"] });
    },
  });

  const webhookMutation = useMutation({
    mutationFn: (url: string) => api.telegramSetWebhook(url),
    onSuccess: (data: any) => {
      setWebhookResult(data);
      qc.invalidateQueries({ queryKey: ["telegram-status"] });
    },
  });

  const handleTest = () => {
    if (!testMsg.trim()) return;
    testMutation.mutate(testMsg.trim());
    setTestMsg("");
  };

  const handleWebhook = () => {
    if (!webhookUrl.trim()) return;
    webhookMutation.mutate(webhookUrl.trim());
  };

  const botInfo = (status as any)?.botInfo;
  const webhookInfo = (status as any)?.webhookInfo;
  const configured = (status as any)?.configured;
  const devUrl = `${window.location.protocol}//${window.location.hostname}:3003/api/telegram/webhook`;

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
          Real-time market data via Telegram with natural language support.
        </p>
      </div>

      {/* Status Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-gray-400 mb-1">Bot Status</p>
            <StatusBadge ok={!!configured} label={configured ? "Token Set" : "Not Configured"} />
            {botInfo?.username && (
              <p className="text-sm text-gray-600 mt-2 font-medium">@{botInfo.username}</p>
            )}
            {botInfo?.error && <p className="text-xs text-red-500 mt-1">{botInfo.error}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-gray-400 mb-1">Webhook</p>
            <StatusBadge ok={!!webhookInfo?.hasWebhook} label={webhookInfo?.hasWebhook ? "Active" : "Not Set"} />
            {webhookInfo?.pendingUpdates > 0 && (
              <p className="text-xs text-amber-600 mt-1">{webhookInfo.pendingUpdates} pending updates</p>
            )}
            {webhookInfo?.lastError && (
              <p className="text-xs text-red-500 mt-1 truncate" title={webhookInfo.lastError}>{webhookInfo.lastError}</p>
            )}
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
              <li>Restart the Python Backend workflow</li>
              <li>Come back here and set the webhook URL (see below)</li>
            </ol>
          </CardContent>
        </Card>
      )}

      {/* Webhook Setup */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Webhook className="w-4 h-4 text-purple-500" /> Set Webhook URL
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-gray-500">
            Paste this URL below (or your deployed URL). Telegram will POST messages to it.
          </p>
          <div className="bg-gray-50 border rounded px-3 py-2 font-mono text-xs text-gray-700 break-all select-all">
            {devUrl}
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="https://your-domain.replit.app/api/telegram/webhook"
              value={webhookUrl}
              onChange={e => setWebhookUrl(e.target.value)}
              className="font-mono text-xs"
              onKeyDown={e => e.key === "Enter" && handleWebhook()}
            />
            <Button
              onClick={handleWebhook}
              disabled={!webhookUrl.trim() || webhookMutation.isPending || !configured}
              size="sm"
            >
              Set
            </Button>
          </div>
          {webhookResult && (
            <div className={`text-sm px-3 py-2 rounded ${webhookResult.success ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
              {webhookResult.success ? "✅ Webhook set successfully!" : `❌ ${webhookResult.description}`}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Test Panel */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <MessageSquare className="w-4 h-4 text-green-500" /> Test Bot (No Telegram needed)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Input
              placeholder="/analyze RELIANCE, !help, which sectors are up?"
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
          {testResult && (
            <div className="space-y-2">
              <div className="bg-gray-50 rounded px-3 py-2 text-sm text-gray-600">
                <span className="text-xs text-gray-400 block mb-0.5">You sent:</span>
                {testResult.text}
              </div>
              <div className="bg-blue-50 rounded px-3 py-2 text-sm text-gray-800 whitespace-pre-wrap">
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
            <strong>Natural language also works:</strong> Just type "analyze RELIANCE", "which sectors are up?",
            "show bullish patterns", "where to invest today?" — the bot understands plain English.
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
