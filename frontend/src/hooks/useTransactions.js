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
      const result = await api.getTransactions(filters);
      setData(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [JSON.stringify(filters)]);

  useEffect(() => { load(); }, [load]);

  const create = async (tx) => { await api.createTransaction(tx); load(); };
  const update = async (id, tx) => { await api.updateTransaction(id, tx); load(); };
  const remove = async (id) => { await api.deleteTransaction(id); load(); };

  return { data, filters, setFilters, loading, error, reload: load, create, update, remove };
}
