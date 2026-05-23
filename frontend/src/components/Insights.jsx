import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Sparkles, TrendingUp, BarChart2, Bot, RefreshCw, AlertCircle, Scale } from 'lucide-react';

export default function Insights() {
  const [vendors, setVendors] = useState([]);
  const [freq, setFreq] = useState([]);
  const [aiInsight, setAiInsight] = useState('');
  const [provider, setProvider] = useState(null);
  const [comparisons, setComparisons] = useState([]);
  const [savingsTips, setSavingsTips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.getPatterns(),
      api.getSavings(),
      api.getComparisons(),
    ])
      .then(([patterns, tips, comp]) => {
        setVendors(patterns || []);
        setSavingsTips(tips || []);
        setComparisons(comp || []);
      })
      .catch(console.error).finally(() => setLoading(false));
  }, []);

  const handleAnalyze = async () => {
    setAiLoading(true);
    try {
      const tips = await api.getSavings();
      setSavingsTips(tips || []);
    } catch (e) { console.error(e); }
    finally { setAiLoading(false); }
  };

  const maxSpend = vendors.length > 0 ? Math.max(...vendors.map(v => v.total || 0)) : 1;

  return (
    <div className="space-y-6">
      {/* Top Vendors */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp size={18} className="text-blue-500" /> Top Vendors (90 days)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10" />)}
              </div>
            ) : vendors.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-muted-foreground gap-2">
                <AlertCircle size={32} strokeWidth={1.5} />
                <p className="text-sm">No spending data yet.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {vendors.map((v, i) => (
                  <div key={v.vendor} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground font-mono text-xs w-4">{i + 1}</span>
                        <span className="font-medium">{v.vendor}</span>
                        <Badge variant="outline" className="text-xs">{v.trips} trips</Badge>
                      </div>
                      <span className="font-mono font-semibold">${(v.total || 0).toFixed(2)}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                      <div className="h-full rounded-full bg-blue-500 transition-all duration-500"
                        style={{ width: `${((v.total || 0) / maxSpend) * 100}%` }}
                        role="progressbar"
                        aria-valuenow={Math.round(((v.total || 0) / maxSpend) * 100)}
                        aria-valuemin="0"
                        aria-valuemax="100"
                        aria-label={`Percentage of maximum spending at ${v.vendor}`}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Frequency */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <BarChart2 size={18} className="text-emerald-500" /> Shopping Frequency
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10" />)}
              </div>
            ) : freq.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-muted-foreground gap-2">
                <AlertCircle size={32} strokeWidth={1.5} />
                <p className="text-sm">No frequency data yet.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {freq.map(f => (
                  <div key={f.vendor} className="flex items-center justify-between p-3 rounded-lg bg-muted/40 hover:bg-muted/70 transition-colors">
                    <span className="text-sm font-medium">{f.vendor}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-muted-foreground">{f.last_visit}</span>
                      <Badge variant="secondary">{f.visits}×</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* AI Coach */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Bot size={18} className="text-purple-500" /> AI Spending Coach
            </CardTitle>
            <div className="flex items-center gap-2">
              {provider && (
                <Badge variant="outline" className="text-xs">
                  <Sparkles size={10} className="mr-1" />
                  {provider.provider}
                </Badge>
              )}
              <Button variant="outline" size="sm" onClick={handleAnalyze} disabled={aiLoading}>
                {aiLoading ? (
                  <><RefreshCw size={14} className="animate-spin" /> Analyzing...</>
                ) : (
                  <><Sparkles size={14} /> Analyze</>
                )}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {aiInsight ? (
            <div className="prose prose-sm max-w-none">
              <div className="rounded-lg bg-gradient-to-br from-purple-50 to-blue-50 border border-purple-100 p-4">
                <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">{aiInsight}</p>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-center gap-3">
              <div className="h-14 w-14 rounded-2xl bg-purple-50 flex items-center justify-center">
                <Bot size={28} className="text-purple-400" strokeWidth={1.5} />
              </div>
              <p className="text-sm font-medium text-foreground">Your AI coach is ready</p>
              <p className="text-xs text-muted-foreground max-w-64">Click "Analyze" to get personalized insights based on your spending patterns.</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Price Compare & Savings Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Price Comparison Section */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Scale size={18} className="text-emerald-500" /> Price Comparison ($/unit)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {comparisons.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-muted-foreground gap-2">
                <AlertCircle size={32} strokeWidth={1.5} />
                <p className="text-sm">No comparisons available yet. Import bills from multiple stores to see price comparisons.</p>
              </div>
            ) : (
              comparisons.map(item => (
                <div key={item.product_id} className="space-y-2 p-3 rounded-lg border">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{item.canonical_name}</span>
                    <Badge variant="outline" className="text-emerald-600 bg-emerald-50 border-emerald-200">
                      Save ${item.potential_monthly_saving?.toFixed(2)}/mo
                    </Badge>
                  </div>
                  {/* Per-store bars */}
                  {Object.entries(JSON.parse(item.store_breakdown)).map(([storeId, data]) => (
                    <div key={storeId} className="flex items-center gap-3">
                      <span className="text-xs w-20 text-muted-foreground truncate">{data.store_name}</span>
                      <div className="flex-1 bg-muted rounded-full h-3 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            data.avg_price_per_std_unit === item.cheapest_price_per_unit
                              ? 'bg-emerald-500' : 'bg-orange-400'
                          }`}
                          style={{ width: `${(data.avg_price_per_std_unit / item.most_expensive_price_per_unit) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono w-24 text-right">
                        ${data.avg_price_per_std_unit.toFixed(3)}/{item.standard_unit}
                      </span>
                    </div>
                  ))}
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Savings Opportunities */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles size={18} className="text-emerald-500" /> Savings Opportunities
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {savingsTips.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-muted-foreground gap-2">
                <AlertCircle size={32} strokeWidth={1.5} />
                <p className="text-sm">No savings opportunities found yet. Import more data to enable cross-store analytics.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {savingsTips.map(tip => (
                  <div key={tip.product_id} className="p-3 rounded-lg bg-emerald-50/50 border border-emerald-100 flex items-start gap-3">
                    <div className="h-8 w-8 rounded-full bg-emerald-100 flex items-center justify-center shrink-0 mt-0.5">
                      <TrendingUp size={14} className="text-emerald-600" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium">{tip.canonical_name}</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Buy at <strong className="text-emerald-700">{tip.cheapest_store_name}</strong> instead of <strong className="text-orange-700">{tip.most_expensive_store_name}</strong>.
                        Save <strong className="text-emerald-700">${tip.potential_monthly_saving?.toFixed(2)}/month</strong> (cheaper by {tip.price_diff_pct}% per {tip.standard_unit}).
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
