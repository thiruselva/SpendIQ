import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip,
  PieChart, Pie, Cell, Legend
} from 'recharts';
import { DollarSign, ShoppingBag, TrendingUp, Calendar, AlertCircle, TrendingDown } from 'lucide-react';

const CATEGORY_COLORS = {
  grocery: '#10b981', food: '#f97316', shopping: '#3b82f6',
  subscription: '#a855f7', health: '#f43f5e', dental: '#06b6d4', other: '#6b7280',
  Costco: '#3b82f6', Walmart: '#f59e0b',
};

function KpiCard({ title, value, sub, icon: Icon, color }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-1">{value}</p>
            {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
          </div>
          <div className={`h-12 w-12 rounded-xl flex items-center justify-center ${color}`}>
            <Icon size={22} className="text-white" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-card p-3 shadow-lg">
      <p className="font-medium text-sm mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="text-sm" style={{ color: p.color }}>
          ${p.value?.toFixed(2)}
        </p>
      ))}
    </div>
  );
};

export default function Overview() {
  const [summary, setSummary] = useState(null);
  const [breakdown, setBreakdown] = useState([]);
  const [trend, setTrend] = useState([]);
  const [quick, setQuick] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.v2GetSummary(), api.v2GetCategoryBreakdown(), api.v2GetMonthlyTrend(), api.getQuickInsights()
    ]).then(([s, b, t, q]) => {
      setSummary(s); setBreakdown(b); setTrend(t); setQuick(q);
    }).catch(console.error).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}><CardContent className="pt-6"><Skeleton className="h-20" /></CardContent></Card>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card><CardContent className="pt-6"><Skeleton className="h-64" /></CardContent></Card>
          <Card><CardContent className="pt-6"><Skeleton className="h-64" /></CardContent></Card>
        </div>
      </div>
    );
  }

  const showSavings = summary?.savings && summary.savings.total_monthly_savings > 0;
  const pieData = breakdown.map(b => ({ name: b.store || b.category, value: b.total, color: CATEGORY_COLORS[b.store] || CATEGORY_COLORS[b.category] || '#6b7280' }));

  return (
    <div className="space-y-6">
      {/* KPI Row */}
      <div className={`grid grid-cols-1 sm:grid-cols-2 ${showSavings ? 'xl:grid-cols-5' : 'xl:grid-cols-4'} gap-4`}>
        <KpiCard title="Total Spent (30d)" value={summary ? `$${summary.total_30d?.toFixed(2) || '0.00'}` : '-'} sub="Last 30 days" icon={DollarSign} color="bg-blue-500" />
        <KpiCard title="Total Spent (90d)" value={summary ? `$${summary.total_90d?.toFixed(2) || '0.00'}` : '-'} sub="Last 90 days" icon={TrendingUp} color="bg-emerald-500" />
        <KpiCard title="Transactions" value={summary?.count_90d ?? '-'} sub="Last 90 days" icon={ShoppingBag} color="bg-orange-500" />
        <KpiCard title="Avg / Transaction" value={summary ? `$${summary.avg_order?.toFixed(2) || '0.00'}` : '-'} sub="90-day average" icon={Calendar} color="bg-purple-500" />
        
        {/* Savings Potential KPI */}
        {showSavings && (
          <Card>
            <CardContent className="pt-6 flex justify-between items-center">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Monthly Savings Potential</p>
                <p className="text-2xl font-bold mt-1 text-emerald-600">
                  ${summary.savings.total_monthly_savings.toFixed(2)}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  across {summary.savings.products_compared} products
                </p>
              </div>
              <div className="h-12 w-12 rounded-xl flex items-center justify-center bg-emerald-500 shrink-0">
                <TrendingDown size={22} className="text-white" />
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Bar Chart */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle className="text-base">Monthly Spending Trend</CardTitle>
          </CardHeader>
          <CardContent>
            {trend.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-52 text-muted-foreground gap-2">
                <AlertCircle size={32} strokeWidth={1.5} />
                <p className="text-sm">No monthly data yet</p>
              </div>
            ) : (
              <>
                <div role="img" aria-label="Bar chart showing monthly spending trend. Visual representation of total spent per month.">
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={trend} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                      <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                      <YAxis tick={{ fontSize: 12 }} />
                      <Tooltip content={<CustomTooltip />} />
                      <Bar dataKey="total" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <table className="sr-only">
                  <caption>Monthly Spending Trend</caption>
                  <thead>
                    <tr>
                      <th scope="col">Month</th>
                      <th scope="col">Total Spent</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trend.map(t => (
                      <tr key={t.month}>
                        <td>{t.month}</td>
                        <td>${(t.total || 0).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </CardContent>
        </Card>

        {/* Pie Chart */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Spending by Store</CardTitle>
          </CardHeader>
          <CardContent>
            {pieData.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-52 text-muted-foreground gap-2">
                <AlertCircle size={32} strokeWidth={1.5} />
                <p className="text-sm">No store data yet</p>
              </div>
            ) : (
              <>
                <div role="img" aria-label="Pie chart showing spending by store. Visual representation of store breakdown.">
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={pieData} cx="50%" cy="45%" innerRadius={55} outerRadius={80} dataKey="value" paddingAngle={2}>
                        {pieData.map((entry, i) => (
                          <Cell key={i} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(v) => `$${v.toFixed(2)}`} />
                      <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '12px' }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <table className="sr-only">
                  <caption>Spending by Store</caption>
                  <thead>
                    <tr>
                      <th scope="col">Store</th>
                      <th scope="col">Total Spent</th>
                    </tr>
                  </thead>
                  <tbody>
                    {breakdown.map(b => (
                      <tr key={b.store || b.category}>
                        <td>{b.store || b.category}</td>
                        <td>${(b.total || 0).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Quick Insights */}
      {quick.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Quick Insights</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {quick.map((insight, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                  <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center shrink-0 mt-0.5">
                    <TrendingUp size={14} className="text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{insight.label}</p>
                    <p className="text-sm text-muted-foreground">{insight.value}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
