const BASE = '/api/v2';

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
  // ── Orders (replaces V1 transactions) ──
  getOrders: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([,v]) => v)).toString();
    return request(`/orders${q ? '?' + q : ''}`);
  },
  getOrderItems: (id) => request(`/orders/${id}/items`),

  // ── Import ──
  importBill: (file) => {
    const form = new FormData();
    form.append('file', file);
    return fetch(`${BASE}/import/bills`, { method: 'POST', body: form }).then(r => r.json());
  },

  // ── Products ──
  getProducts: (search = '') => request(`/products${search ? '?search=' + encodeURIComponent(search) : ''}`),
  getProductPrices: (id) => request(`/products/${id}/prices`),

  // ── Dashboard ──
  getSummary: () => request('/dashboard/summary'),
  getCategoryBreakdown: () => request('/dashboard/category-breakdown'),
  getMonthlyTrend: () => request('/dashboard/monthly-trend'),

  // ── Insights ──
  getPatterns: (store = '') => request(`/insights/patterns${store ? '?store=' + encodeURIComponent(store) : ''}`),
  getComparisons: () => request('/insights/comparisons'),
  getSavings: () => request('/insights/savings'),

  // ── Shopping Lists ──
  generateShoppingList: (store = 'Costco', periodType = 'weekly') =>
    request(`/shopping-list/generate?store=${encodeURIComponent(store)}&period_type=${periodType}`, { method: 'POST' }),
  getShoppingList: (listId) => request(`/shopping-list/${listId}`),
  submitFeedback: (listId, feedback) =>
    request(`/shopping-list/${listId}/feedback`, { method: 'PUT', body: JSON.stringify(feedback) }),
};
