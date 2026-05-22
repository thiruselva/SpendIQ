import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Plus, Sparkles, Copy, Trash2, ShoppingCart, CheckCircle2 } from 'lucide-react';

export default function ShoppingList() {
  const [tab, setTab] = useState('weekly');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiMessage, setAiMessage] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [newItem, setNewItem] = useState({ item: '', store: 'Costco', frequency: 'Every week', est_price: '', list_type: 'weekly' });

  const load = (t = tab) => {
    setLoading(true);
    api.getShoppingList(t).then(setItems).catch(console.error).finally(() => setLoading(false));
  };

  useEffect(() => { load(tab); }, [tab]);

  const handleToggle = async (id, done) => {
    await api.updateShoppingItem(id, { is_done: done ? 0 : 1 });
    load();
  };

  const handleDelete = async (id) => {
    await api.deleteShoppingItem(id);
    load();
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    await api.addShoppingItem({ ...newItem, est_price: newItem.est_price ? parseFloat(newItem.est_price) : null, list_type: tab });
    setShowAdd(false);
    setNewItem({ item: '', store: 'Costco', frequency: 'Every week', est_price: '', list_type: 'weekly' });
    load();
  };

  const handleAiGenerate = async () => {
    setAiLoading(true);
    setAiMessage('');
    try {
      const result = await api.generateShoppingList();
      setAiMessage(result.message || 'Done!');
      load();
      setTimeout(() => setAiMessage(''), 6000);
    } catch (e) {
      setAiMessage('Error: ' + (e.message || 'Failed'));
    } finally {
      setAiLoading(false);
    }
  };

  const handleCopy = () => {
    const grouped = {};
    items.filter(i => !i.is_done).forEach(i => {
      const store = i.store || 'Other';
      if (!grouped[store]) grouped[store] = [];
      grouped[store].push(`☐ ${i.item}${i.est_price ? ` ~$${i.est_price}` : ''}`);
    });
    const text = Object.entries(grouped).map(([store, list]) => `── ${store.toUpperCase()} ──\n${list.join('\n')}`).join('\n\n');
    navigator.clipboard.writeText(text);
  };

  // Group by store
  const grouped = {};
  items.forEach(i => {
    const s = i.store || 'Other';
    if (!grouped[s]) grouped[s] = [];
    grouped[s].push(i);
  });

  const doneCount = items.filter(i => i.is_done).length;

  return (
    <div className="space-y-4">
      {/* Header actions */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="weekly">Weekly</TabsTrigger>
            <TabsTrigger value="monthly">Monthly</TabsTrigger>
            <TabsTrigger value="subscriptions">Subscriptions</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleAiGenerate} disabled={aiLoading}>
            {aiLoading ? <><Sparkles size={14} className="animate-pulse" /> Generating...</> : <><Sparkles size={14} /> AI Generate</>}
          </Button>
          <Button variant="outline" size="sm" onClick={handleCopy} disabled={items.length === 0}>
            <Copy size={14} /> Copy List
          </Button>
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus size={14} /> Add Item
          </Button>
        </div>
      </div>

      {/* AI feedback */}
      {aiMessage && (
        <div className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm border ${
          aiMessage.startsWith('Error')
            ? 'bg-destructive/10 text-destructive border-destructive/20'
            : 'bg-emerald-50 text-emerald-700 border-emerald-200'
        }`}>
          {aiMessage.startsWith('Error') ? '⚠️' : '✅'} {aiMessage}
        </div>
      )}

      {/* Progress summary */}
      {items.length > 0 && (
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <CheckCircle2 size={16} className="text-emerald-500" />
          {doneCount}/{items.length} items checked off
        </div>
      )}

      {/* Items */}
      {loading ? (
        <Card><CardContent className="pt-6">
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-10 rounded-lg bg-muted animate-pulse" />
            ))}
          </div>
        </CardContent></Card>
      ) : items.length === 0 ? (
        <Card><CardContent className="py-16">
          <div className="flex flex-col items-center gap-3 text-center">
            <ShoppingCart size={40} strokeWidth={1.5} className="text-muted-foreground" />
            <p className="text-sm font-medium">No items yet</p>
            <p className="text-xs text-muted-foreground">Add items manually or let AI generate your shopping list</p>
            <Button size="sm" onClick={() => setShowAdd(true)}><Plus size={14} /> Add First Item</Button>
          </div>
        </CardContent></Card>
      ) : (
        Object.entries(grouped).map(([store, storeItems]) => (
          <Card key={store}>
            <CardHeader className="py-3 px-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  🏪 {store}
                </CardTitle>
                <Badge variant="secondary" className="text-xs">{storeItems.length} items</Badge>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0 space-y-1">
              {storeItems.map(item => (
                <div key={item.id} className={`group flex items-center gap-3 p-2.5 rounded-lg transition-colors hover:bg-muted/40 ${item.is_done ? 'opacity-50' : ''}`}>
                  <Checkbox
                    id={`item-cb-${item.id}`}
                    checked={!!item.is_done}
                    onCheckedChange={() => handleToggle(item.id, item.is_done)}
                  />
                  <label
                    htmlFor={`item-cb-${item.id}`}
                    className={`flex-1 text-sm cursor-pointer ${item.is_done ? 'line-through text-muted-foreground' : ''}`}
                  >
                    {item.item}
                  </label>
                  {item.frequency && (
                    <span className="text-xs text-muted-foreground hidden sm:block">{item.frequency}</span>
                  )}
                  {item.est_price && (
                    <span className="text-xs font-mono font-medium">~${item.est_price}</span>
                  )}
                  <Button variant="ghost" size="icon" className="h-6 w-6 opacity-0 group-hover:opacity-100 hover:opacity-100 focus-visible:opacity-100 group-focus-within:opacity-100 text-destructive hover:text-destructive"
                    onClick={() => handleDelete(item.id)}
                    aria-label={`Delete ${item.item}`}
                  >
                    <Trash2 size={13} />
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        ))
      )}

      {/* Add Item Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add Shopping Item</DialogTitle></DialogHeader>
          <form onSubmit={handleAdd} className="space-y-4 mt-2">
            <div className="space-y-1.5">
              <label htmlFor="new-item-name" className="text-sm font-medium">Item</label>
              <Input id="new-item-name" placeholder="e.g. Whole milk (1 gallon)" value={newItem.item}
                onChange={e => setNewItem(n => ({ ...n, item: e.target.value }))} required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label htmlFor="new-item-store" className="text-sm font-medium">Store</label>
                <Select value={newItem.store} onValueChange={v => setNewItem(n => ({ ...n, store: v }))}>
                  <SelectTrigger id="new-item-store"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['Costco', 'Walmart', 'Target', 'Amazon', 'Local Grocer', 'Other'].map(s => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="new-item-freq" className="text-sm font-medium">Frequency</label>
                <Select value={newItem.frequency} onValueChange={v => setNewItem(n => ({ ...n, frequency: v }))}>
                  <SelectTrigger id="new-item-freq"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['Every week', 'Bi-weekly', 'Monthly', 'As needed'].map(f => (
                      <SelectItem key={f} value={f}>{f}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="new-item-price" className="text-sm font-medium">Estimated Price ($)</label>
              <Input id="new-item-price" type="number" step="0.01" placeholder="Optional" value={newItem.est_price}
                onChange={e => setNewItem(n => ({ ...n, est_price: e.target.value }))} />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button type="submit">Add Item</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
