import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend
} from 'recharts';
import { Search, Scale, TrendingUp, AlertCircle, Sparkles, CheckCircle2 } from 'lucide-react';

export default function PriceCompare() {
  const [searchTerm, setSearchTerm] = useState('');
  const [products, setProducts] = useState([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [monthlyUnits, setMonthlyUnits] = useState(16); // Default default monthly consumption

  // Search products on mount or when searchTerm changes
  useEffect(() => {
    setLoadingProducts(true);
    const delay = setTimeout(() => {
      api.v2GetProducts(searchTerm)
        .then(setProducts)
        .catch(console.error)
        .finally(() => setLoadingProducts(false));
    }, 300);
    return () => clearTimeout(delay);
  }, [searchTerm]);

  const handleSelectProduct = async (product) => {
    setSelectedProduct(product);
    setLoadingHistory(true);
    try {
      const history = await api.v2GetProductPrices(product.id);
      setPriceHistory(history || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingHistory(false);
    }
  };

  // Group price history by store to find the latest prices and info
  const latestStorePrices = {};
  priceHistory.forEach(price => {
    const store = price.store_name;
    if (!latestStorePrices[store] || new Date(price.recorded_date) > new Date(latestStorePrices[store].recorded_date)) {
      latestStorePrices[store] = price;
    }
  });

  const stores = Object.keys(latestStorePrices);
  let cheapestStore = null;
  let lowestPpu = Infinity;

  stores.forEach(store => {
    const ppu = latestStorePrices[store].price_per_standard_unit;
    if (ppu < lowestPpu) {
      lowestPpu = ppu;
      cheapestStore = store;
    }
  });

  // Prepare data for the LineChart (grouped by date)
  // Format needed: [{ date: '2026-05-01', Costco: 0.304, Walmart: 0.586 }]
  const dateMap = {};
  priceHistory.forEach(price => {
    const date = price.recorded_date;
    if (!dateMap[date]) {
      dateMap[date] = { date };
    }
    dateMap[date][price.store_name] = price.price_per_standard_unit;
  });

  const chartData = Object.values(dateMap).sort((a, b) => new Date(a.date) - new Date(b.date));

  const standardUnit = selectedProduct?.standard_unit || 'unit';

  return (
    <div className="space-y-6">
      {/* Search Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight">Cross-Store Price Comparison</h2>
          <p className="text-sm text-muted-foreground">Compare unit-normalized prices ($/oz, $/fl_oz) side-by-side.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {/* Left Column: Product Search */}
        <Card className="md:col-span-1 h-[calc(100vh-220px)] flex flex-col overflow-hidden">
          <CardHeader className="py-4">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                type="search"
                placeholder="Search products..."
                className="pl-8 text-sm"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
              />
            </div>
          </CardHeader>
          <CardContent className="flex-1 overflow-y-auto px-4 pb-4 pt-0 space-y-1">
            {loadingProducts && products.length === 0 ? (
              <div className="space-y-2 py-4">
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
              </div>
            ) : products.length === 0 ? (
              <div className="text-xs text-muted-foreground text-center py-8">
                No products found.
              </div>
            ) : (
              products.map(p => (
                <button
                  key={p.id}
                  onClick={() => handleSelectProduct(p)}
                  className={`w-full text-left p-2.5 rounded-lg text-sm font-medium transition-colors flex items-center justify-between ${
                    selectedProduct?.id === p.id
                      ? 'bg-blue-600 text-white'
                      : 'hover:bg-muted text-foreground'
                  }`}
                >
                  <div className="truncate pr-2">
                    <span className="block truncate">{p.canonical_name}</span>
                    {p.brand && <span className={`text-xs block ${selectedProduct?.id === p.id ? 'text-blue-200' : 'text-muted-foreground'}`}>{p.brand}</span>}
                  </div>
                  <Badge variant="outline" className={`text-xs ${selectedProduct?.id === p.id ? 'border-blue-400 text-white' : ''}`}>
                    {p.store_count} {p.store_count === 1 ? 'store' : 'stores'}
                  </Badge>
                </button>
              ))
            )}
          </CardContent>
        </Card>

        {/* Right Column: Comparison Details */}
        <div className="md:col-span-3 space-y-6">
          {!selectedProduct ? (
            <Card className="h-full flex items-center justify-center py-24 border-dashed">
              <div className="text-center space-y-3">
                <div className="h-12 w-12 rounded-2xl bg-blue-50 flex items-center justify-center mx-auto text-blue-500">
                  <Scale size={24} />
                </div>
                <p className="text-sm font-medium text-foreground">No Product Selected</p>
                <p className="text-xs text-muted-foreground max-w-72">Select a product from the list on the left to see unit comparisons, price trends, and monthly cost projections.</p>
              </div>
            </Card>
          ) : (
            <>
              {/* Product Info & Store Cards */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-semibold">{selectedProduct.canonical_name}</h3>
                  {selectedProduct.brand && <Badge variant="secondary">{selectedProduct.brand}</Badge>}
                  <Badge variant="outline" className="font-mono">Standard Unit: {standardUnit}</Badge>
                </div>

                {loadingHistory ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Skeleton className="h-32" />
                    <Skeleton className="h-32" />
                  </div>
                ) : stores.length === 0 ? (
                  <Card className="p-6 text-center text-sm text-muted-foreground">
                    No price history observations found for this product.
                  </Card>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {stores.map(store => {
                      const latest = latestStorePrices[store];
                      const isCheapest = store === cheapestStore;
                      const sizeDesc = latest.package_size
                        ? `${latest.package_count > 1 ? `${latest.package_count}x` : ''}${latest.package_size} ${latest.package_unit}`
                        : 'standard';
                      const ppu = latest.price_per_standard_unit;

                      return (
                        <Card key={store} className={`relative overflow-hidden transition-all ${
                          isCheapest ? 'border-emerald-500 shadow-md ring-1 ring-emerald-500/25 bg-emerald-50/5' : ''
                        }`}>
                          {isCheapest && (
                            <div className="absolute right-0 top-0 bg-emerald-500 text-white text-[10px] uppercase font-bold py-1 px-3.5 rounded-bl-lg flex items-center gap-1">
                              <CheckCircle2 size={10} /> Best Value
                            </div>
                          )}
                          <CardHeader className="pb-2">
                            <span className="text-xs text-muted-foreground uppercase font-bold tracking-wider">{store}</span>
                            <CardTitle className="text-sm font-semibold">{selectedProduct.canonical_name}</CardTitle>
                          </CardHeader>
                          <CardContent className="space-y-2">
                            <div className="flex items-baseline justify-between">
                              <span className="text-2xl font-bold font-mono">
                                ${ppu?.toFixed(3)}<span className="text-xs text-muted-foreground font-normal">/{standardUnit}</span>
                              </span>
                              <span className="text-sm font-mono text-muted-foreground">
                                Pack: ${latest.raw_price?.toFixed(2)} ({sizeDesc})
                              </span>
                            </div>
                            <span className="text-xs text-muted-foreground block">
                              Last observed: {latest.recorded_date}
                            </span>
                          </CardContent>
                        </Card>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Monthly Cost & Savings Projection */}
              {!loadingHistory && stores.length >= 2 && (
                <Card className="bg-gradient-to-r from-emerald-500/5 to-teal-500/5 border-emerald-100">
                  <CardHeader className="py-4">
                    <CardTitle className="text-sm font-bold flex items-center gap-1.5 text-emerald-800">
                      <Sparkles size={16} /> Monthly Consumption Projection
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-semibold text-muted-foreground">Configure Monthly Usage:</span>
                      <div className="flex items-center gap-1.5">
                        <Input
                          type="number"
                          className="w-20 h-8 text-xs font-mono font-bold"
                          value={monthlyUnits}
                          onChange={e => setMonthlyUnits(Math.max(1, parseFloat(e.target.value) || 1))}
                        />
                        <span className="text-xs font-semibold text-muted-foreground">{standardUnit}s</span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-4 text-sm font-semibold">
                      {stores.map(store => {
                        const ppu = latestStorePrices[store].price_per_standard_unit;
                        const monthlyCost = ppu * monthlyUnits;
                        const isCheapest = store === cheapestStore;

                        return (
                          <div key={store} className="flex flex-col">
                            <span className="text-[10px] uppercase text-muted-foreground">{store} Cost</span>
                            <span className={`font-mono text-base ${isCheapest ? 'text-emerald-600 font-bold' : ''}`}>
                              ${monthlyCost.toFixed(2)}/mo
                            </span>
                          </div>
                        );
                      })}

                      {/* Potential Savings */}
                      <div className="flex flex-col pl-4 border-l">
                        <span className="text-[10px] uppercase text-emerald-800 font-bold">Estimated Saving</span>
                        <span className="font-mono text-base text-emerald-600 font-bold">
                          ${(Math.max(0, ...stores.map(s => latestStorePrices[s].price_per_standard_unit * monthlyUnits)) -
                            (lowestPpu * monthlyUnits)).toFixed(2)}/mo
                        </span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Price Trend Chart */}
              {!loadingHistory && chartData.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                      <TrendingUp size={18} className="text-blue-500" /> Unit Price Trend Over Time ($/{standardUnit})
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pt-2">
                    <div className="h-64" role="img" aria-label="Line chart showing unit price trends over time for the selected product across different stores.">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                          <YAxis tick={{ fontSize: 11 }} />
                          <Tooltip formatter={(v) => [`$${v.toFixed(3)}`, '']} labelClassName="text-xs" />
                          <Legend wrapperStyle={{ fontSize: '12px', marginTop: '10px' }} />
                          
                          <Line
                            type="monotone"
                            dataKey="Costco"
                            stroke="#3b82f6"
                            strokeWidth={2}
                            activeDot={{ r: 6 }}
                            connectNulls
                          />
                          <Line
                            type="monotone"
                            dataKey="Walmart"
                            stroke="#f59e0b"
                            strokeWidth={2}
                            activeDot={{ r: 6 }}
                            connectNulls
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
