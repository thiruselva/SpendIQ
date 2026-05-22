const BASE = '/api';

async function request(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  // Transactions
  getTransactions: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([,v]) => v)).toString();
    return request(`/transactions${q ? '?' + q : ''}`);
  },
  createTransaction: (data) => request('/transactions', { method: 'POST', body: JSON.stringify(data) }),
  updateTransaction: (id, data) => request(`/transactions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTransaction: (id) => request(`/transactions/${id}`, { method: 'DELETE' }),
  getTransactionItems: (id) => request(`/transactions/${id}/items`),

  // Dashboard
  getSummary: () => request('/dashboard/summary'),
  getCategoryBreakdown: () => request('/dashboard/category-breakdown'),
  getMonthlyTrend: () => request('/dashboard/monthly-trend'),

  // Insights
  getTopVendors: (days = 90) => request(`/insights/top-vendors?days=${days}`),
  getFrequency: () => request('/insights/frequency'),
  getQuickInsights: () => request('/insights/quick'),

  // Shopping List
  getShoppingList: (type) => request(`/shopping-list${type ? '?list_type=' + type : ''}`),
  addShoppingItem: (data) => request('/shopping-list', { method: 'POST', body: JSON.stringify(data) }),
  updateShoppingItem: (id, data) => request(`/shopping-list/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteShoppingItem: (id) => request(`/shopping-list/${id}`, { method: 'DELETE' }),

  // AI
  analyzeSpending: () => request('/ai/analyze', { method: 'POST' }),
  generateShoppingList: () => request('/ai/shopping-list', { method: 'POST' }),
  getAiProvider: () => request('/ai/provider'),

  // Import
  importPdf: (file) => {
    const form = new FormData();
    form.append('file', file);
    return fetch(`${BASE}/import/pdf`, { method: 'POST', body: form }).then(r => r.json());
  },
  importCsv: (file) => {
    const form = new FormData();
    form.append('file', file);
    return fetch(`${BASE}/import/csv`, { method: 'POST', body: form }).then(r => r.json());
  },

  // Utility
  getCategories: () => request('/categories'),
  getSources: () => request('/sources'),
  getMonths: () => request('/months'),
};
