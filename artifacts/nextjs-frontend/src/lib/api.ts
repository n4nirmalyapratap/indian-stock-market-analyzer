import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api`
  : '/api';

export const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const api = {
  // Health
  health: () => apiClient.get('/health'),

  // Sectors
  sectors: {
    getAll: () => apiClient.get('/sectors'),
    getRotation: () => apiClient.get('/sectors/rotation'),
    getDetail: (symbol: string) => apiClient.get(`/sectors/${encodeURIComponent(symbol)}`),
  },

  // Stocks
  stocks: {
    getDetail: (symbol: string) => apiClient.get(`/stocks/${symbol}`),
    getNifty100: () => apiClient.get('/stocks/nifty100'),
    getMidcap: () => apiClient.get('/stocks/midcap'),
    getSmallcap: () => apiClient.get('/stocks/smallcap'),
  },

  // Patterns
  patterns: {
    getAll: (universe?: string, signal?: string) =>
      apiClient.get('/patterns', { params: { universe, signal } }),
    triggerScan: () => apiClient.post('/patterns/scan'),
  },

  // Scanners
  scanners: {
    getAll: () => apiClient.get('/scanners'),
    getById: (id: string) => apiClient.get(`/scanners/${id}`),
    create: (data: any) => apiClient.post('/scanners', data),
    update: (id: string, data: any) => apiClient.put(`/scanners/${id}`, data),
    delete: (id: string) => apiClient.delete(`/scanners/${id}`),
    run: (id: string) => apiClient.post(`/scanners/${id}/run`),
  },

  // WhatsApp Bot
  whatsapp: {
    getStatus: () => apiClient.get('/whatsapp/status'),
    sendMessage: (data: any) => apiClient.post('/whatsapp/message', data),
    getMessages: () => apiClient.get('/whatsapp/messages'),
    generateQr: () => apiClient.post('/whatsapp/qr'),
    updateStatus: (enabled: boolean) => apiClient.put('/whatsapp/status', { enabled }),
  },
};

export default api;
