import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

export function useTransactions(initialFilters = {}) {
  const [data, setData] = useState({ transactions: [], total: 0 });
  const [filters, setFilters] = useState(initialFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const orders = await api.getOrders(filters);
      setData({ transactions: orders, total: orders.length });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [JSON.stringify(filters)]);

  useEffect(() => { load(); }, [load]);

  return { data, filters, setFilters, loading, error, reload: load };
}
