import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Sparkles, ShoppingCart, CheckCircle2, Copy, Scale, ArrowRight, Bot, AlertCircle } from 'lucide-react';

export default function ShoppingList() {
  const [store, setStore] = useState('Costco');
  const [periodType, setPeriodType] = useState('weekly');
  const [currentList, setCurrentList] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');

  // Local state for checking items and editing feedback values
  const [itemsState, setItemsState] = useState({});

  const handleGenerate = async () => {
    setGenerating(true);
    setMessage('');
    try {
      const result = await api.v2GenerateShoppingList(store, periodType);
      setCurrentList(result);
      
      // Initialize items state
      const initial = {};
      result.items.forEach(item => {
        initial[item.product_id] = {
          checked: false,
          actualQty: item.predicted_qty || 1,
          actualPrice: item.estimated_price || '',
          note: ''
        };
      });
      setItemsState(initial);
    } catch (e) {
      console.error(e);
      setMessage(`Error: ${e.message || 'Generation failed'}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleToggleItem = (productId, val) => {
    setItemsState(prev => ({
      ...prev,
      [productId]: {
        ...prev[productId],
        checked: val
      }
    }));
  };

  const handleUpdateItemValue = (productId, field, val) => {
    setItemsState(prev => ({
      ...prev,
      [productId]: {
        ...prev[productId],
        [field]: val
      }
    }));
  };

  const handleCompleteShopping = async () => {
    if (!currentList?.list?.id) return;
    setSubmitting(true);
    setMessage('');
    try {
      // Gather feedback from itemsState
      const feedback = currentList.items.map(item => {
        const state = itemsState[item.product_id] || {};
        return {
          product_id: item.product_id,
          was_purchased: state.checked ? 1 : 0,
          actual_qty: state.checked ? parseFloat(state.actualQty) || 0 : null,
          actual_price: state.checked ? parseFloat(state.actualPrice) || 0 : null,
          note: state.note || null
        };
      });

      await api.v2SubmitFeedback(currentList.list.id, feedback);
      setMessage('Shopping trip logged! Intelligence engine re-calibrated.');
      setCurrentList(null); // Clear the list
    } catch (e) {
      console.error(e);
      setMessage(`Error logging feedback: ${e.message || 'Failed'}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCopy = () => {
    if (!currentList?.items) return;
    const lines = [`=== ${store.toUpperCase()} - ${periodType.toUpperCase()} SHOPPING LIST ===`];
    currentList.items.forEach(item => {
      const state = itemsState[item.product_id] || {};
      const prefix = state.checked ? '[x]' : '[ ]';
      const brandStr = item.brand ? ` (${item.brand})` : '';
      const pkgStr = item.package_size ? ` [${item.package_count > 1 ? `${item.package_count}x` : ''}${item.package_size} ${item.package_unit}]` : '';
      lines.push(`${prefix} ${item.canonical_name}${brandStr}${pkgStr} - Qty: ${state.actualQty || item.predicted_qty}`);
    });
    
    if (currentList.tips?.length > 0) {
      lines.push('\n=== SAVINGS TIPS ===');
      currentList.tips.forEach(t => lines.push(`• ${t.description}`));
    }

    navigator.clipboard.writeText(lines.join('\n'));
    setMessage('List copied to clipboard!');
    setTimeout(() => setMessage(''), 3000);
  };

  const getConfidenceBadge = (score) => {
    if (score >= 0.80) {
      return <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">High Confidence</Badge>;
    } else if (score >= 0.50) {
      return <Badge className="bg-amber-100 text-amber-800 border-amber-200">Medium Confidence</Badge>;
    } else {
      return <Badge className="bg-gray-100 text-gray-700 border-gray-200">Low Confidence</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Configuration Header */}
      {!currentList && (
        <Card className="border-none bg-gradient-to-r from-blue-500/10 via-indigo-500/5 to-purple-500/10 backdrop-blur-md">
          <CardContent className="pt-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="space-y-1">
                <h2 className="text-xl font-bold tracking-tight">AI Smart Shopping List</h2>
                <p className="text-sm text-muted-foreground">Select store and period to generate a predictive shopping list.</p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Select value={store} onValueChange={setStore}>
                  <SelectTrigger className="w-36 bg-background">
                    <SelectValue placeholder="Store" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Costco">Costco Wholesale</SelectItem>
                    <SelectItem value="Walmart">Walmart Supercenter</SelectItem>
                  </SelectContent>
                </Select>

                <Tabs value={periodType} onValueChange={setPeriodType} className="bg-background rounded-lg border p-1 h-10 flex items-center">
                  <TabsList className="grid grid-cols-2 w-44 bg-transparent border-none">
                    <TabsTrigger value="weekly" className="h-8">Weekly</TabsTrigger>
                    <TabsTrigger value="monthly" className="h-8">Monthly</TabsTrigger>
                  </TabsList>
                </Tabs>

                <Button onClick={handleGenerate} disabled={generating} className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg">
                  {generating ? (
                    <>Generating...</>
                  ) : (
                    <>
                      <Sparkles size={16} className="mr-1.5" />
                      Generate List
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Message feedback */}
      {message && (
        <div className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm border ${
          message.startsWith('Error')
            ? 'bg-destructive/10 text-destructive border-destructive/20'
            : 'bg-emerald-50 text-emerald-700 border-emerald-200'
        }`}>
          {message.startsWith('Error') ? '⚠️' : '✅'} {message}
        </div>
      )}

      {/* Current List Display */}
      {currentList && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h2 className="text-xl font-bold tracking-tight flex items-center gap-2">
                🏪 {store} Shopping List ({periodType})
              </h2>
              <p className="text-sm text-muted-foreground">Estimated Cost: ${currentList.estimated_total?.toFixed(2)}</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={handleCopy}>
                <Copy size={14} className="mr-1" /> Copy
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setCurrentList(null)}>
                Cancel
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Items Column */}
            <div className="lg:col-span-2 space-y-3">
              {currentList.items.length === 0 ? (
                <Card><CardContent className="py-12 text-center text-muted-foreground">No predictive items found for this store/period.</CardContent></Card>
              ) : (
                currentList.items.map(item => {
                  const state = itemsState[item.product_id] || {};
                  const tip = currentList.tips?.find(t => t.product_id === item.product_id);
                  const pkgDesc = item.package_size ? `${item.package_count > 1 ? `${item.package_count}x` : ''}${item.package_size} ${item.package_unit}` : 'standard';

                  return (
                    <Card key={item.product_id} className={`transition-all ${state.checked ? 'border-blue-200 bg-blue-50/10' : ''}`}>
                      <CardContent className="p-4 space-y-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-start gap-3">
                            <Checkbox
                              id={`item-${item.product_id}`}
                              checked={state.checked}
                              onCheckedChange={(val) => handleToggleItem(item.product_id, !!val)}
                              className="mt-1"
                            />
                            <div>
                              <label htmlFor={`item-${item.product_id}`} className="font-semibold text-sm cursor-pointer hover:text-blue-600 block">
                                {item.canonical_name}
                              </label>
                              {item.brand && <span className="text-xs text-muted-foreground block">{item.brand}</span>}
                              <div className="flex flex-wrap items-center gap-2 mt-1.5">
                                <Badge variant="secondary" className="text-xs">{pkgDesc}</Badge>
                                {item.est_price_per_std_unit && (
                                  <Badge variant="outline" className="text-xs font-mono">
                                    ${item.est_price_per_std_unit.toFixed(3)}/{item.standard_unit || 'unit'}
                                  </Badge>
                                )}
                                {getConfidenceBadge(item.confidence_score)}
                              </div>
                            </div>
                          </div>
                          
                          <div className="text-right">
                            <span className="text-sm font-semibold block">Qty: {item.predicted_qty}</span>
                            {item.estimated_price && (
                              <span className="text-xs text-muted-foreground font-mono block">Est: ${item.estimated_price.toFixed(2)}</span>
                            )}
                          </div>
                        </div>

                        {/* Inline Savings Tip */}
                        {tip && (
                          <div className="text-xs rounded-lg p-2.5 bg-emerald-50/80 border border-emerald-100 flex items-start gap-2 text-emerald-800">
                            <Bot size={14} className="text-emerald-600 shrink-0 mt-0.5" />
                            <p>{tip.description}</p>
                          </div>
                        )}

                        {/* Expandable feedback input fields */}
                        {state.checked && (
                          <div className="pt-3 border-t grid grid-cols-1 sm:grid-cols-3 gap-3 bg-muted/20 p-2.5 rounded-md">
                            <div className="space-y-1">
                              <label className="text-xs font-semibold text-muted-foreground">Actual Qty Bought</label>
                              <Input
                                type="number"
                                size="sm"
                                className="h-8 text-xs font-mono"
                                value={state.actualQty}
                                onChange={e => handleUpdateItemValue(item.product_id, 'actualQty', e.target.value)}
                              />
                            </div>
                            <div className="space-y-1">
                              <label className="text-xs font-semibold text-muted-foreground">Price Paid ($)</label>
                              <Input
                                type="number"
                                step="0.01"
                                size="sm"
                                className="h-8 text-xs font-mono"
                                placeholder={item.estimated_price?.toFixed(2) || '0.00'}
                                value={state.actualPrice}
                                onChange={e => handleUpdateItemValue(item.product_id, 'actualPrice', e.target.value)}
                              />
                            </div>
                            <div className="space-y-1">
                              <label className="text-xs font-semibold text-muted-foreground">Feedback / Notes</label>
                              <Input
                                type="text"
                                size="sm"
                                className="h-8 text-xs"
                                placeholder="Running low? Price change?"
                                value={state.note}
                                onChange={e => handleUpdateItemValue(item.product_id, 'note', e.target.value)}
                              />
                            </div>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  );
                })
              )}
            </div>

            {/* Savings Tips Summary Column */}
            <div className="space-y-4">
              <Card className="border-emerald-200 bg-emerald-50/5">
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Scale size={18} className="text-emerald-600" /> Store Savings Potential
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {currentList.tips?.length === 0 ? (
                    <div className="text-xs text-muted-foreground text-center py-6">
                      No savings comparisons found for items in this shopping list.
                    </div>
                  ) : (
                    currentList.tips.map((tip, i) => (
                      <div key={i} className="p-3 rounded-lg bg-emerald-50/50 border border-emerald-100/50 text-xs space-y-1">
                        <div className="flex items-center justify-between font-semibold text-emerald-800">
                          <span>{tip.canonical_name}</span>
                          <span className="font-mono">Save ${tip.estimated_saving?.toFixed(2)}</span>
                        </div>
                        <p className="text-muted-foreground leading-relaxed">{tip.description}</p>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              {/* Complete Shopping Button */}
              <Button
                onClick={handleCompleteShopping}
                disabled={submitting}
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-6 text-sm shadow-md"
              >
                {submitting ? 'Updating Engine...' : 'Complete Shopping & Log Feedback'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
