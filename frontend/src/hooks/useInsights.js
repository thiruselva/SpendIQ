import { useState, useEffect } from 'react';
import { api } from '../api/client';

export function useInsights() {
  const [summary, setSummary] = useState(null);
  const [categories, setCategories] = useState([]);
  const [trend, setTrend] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [frequency, setFrequency] = useState([]);
  const [quickInsights, setQuickInsights] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getSummary(),
      api.getCategoryBreakdown(),
      api.getMonthlyTrend(),
      api.getTopVendors(),
      api.getFrequency(),
      api.getQuickInsights(),
    ]).then(([s, c, t, v, f, q]) => {
      setSummary(s);
      setCategories(c);
      setTrend(t);
      setVendors(v);
      setFrequency(f);
      setQuickInsights(q);
    }).catch(console.error)
    .finally(() => setLoading(false));
  }, []);

  return { summary, categories, trend, vendors, frequency, quickInsights, loading };
}
