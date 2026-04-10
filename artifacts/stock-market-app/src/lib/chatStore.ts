import { create } from "zustand";

interface ChatStore {
  symbol: string | null;
  open: (symbol: string) => void;
  close: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  symbol: null,
  open: (symbol: string) => set({ symbol: symbol.toUpperCase() }),
  close: () => set({ symbol: null }),
}));
