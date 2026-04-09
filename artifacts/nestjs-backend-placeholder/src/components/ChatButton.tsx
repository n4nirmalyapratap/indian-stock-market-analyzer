import { MessageCircle } from "lucide-react";
import { useChatStore } from "@/lib/chatStore";

interface ChatButtonProps {
  symbol: string;
  className?: string;
}

export default function ChatButton({ symbol, className = "" }: ChatButtonProps) {
  const { open } = useChatStore();
  return (
    <button
      onClick={(e) => { e.stopPropagation(); open(symbol); }}
      title={`Chat about ${symbol}`}
      className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-indigo-400 hover:text-indigo-600 hover:bg-indigo-50 transition flex-shrink-0 ${className}`}
    >
      <MessageCircle className="w-3.5 h-3.5" />
    </button>
  );
}
