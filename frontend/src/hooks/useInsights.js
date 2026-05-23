import { useState, useEffect } from 'react';
import { api } from '../api/client';

export function useInsights() {
  const [summary, setSummary] = useState(null);
  const [categories, setCategories] = useState([]);
  const [trend, setTrend] = useState([]);
  const [patterns, setPatterns] = useState([]);
  const [savings, setSavings] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getSummary(),
      api.getCategoryBreakdown(),
      api.getMonthlyTrend(),
      api.getPatterns(),
      api.getSavings(),
    ]).then(([s, c, t, p, sv]) => {
      setSummary(s);
      setCategories(c);
      setTrend(t);
      setPatterns(p);
      setSavings(sv);
    }).catch(console.error)
    .finally(() => setLoading(false));
  }, []);

  return { summary, categories, trend, patterns, savings, loading };
}
