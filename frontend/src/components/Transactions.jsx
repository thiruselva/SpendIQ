import { useState, useEffect, Fragment } from 'react';
import { api } from '../api/client';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';
import { Plus, Search, Pencil, Trash2, X, Check, ChevronDown, ChevronRight, FileText, Package } from 'lucide-react';

const CATEGORY_VARIANT = { grocery: 'grocery', food: 'food', shopping: 'shopping', subscription: 'subscription', health: 'health', dental: 'dental' };
const CATEGORIES = ['grocery', 'food', 'shopping', 'subscription', 'health', 'dental', 'other'];

export default function Transactions() {
  const [data, setData] = useState({ transactions: [], total: 0 });
  const [filters, setFilters] = useState({ category: '', source: '', month: '', search: '' });
  const [categories, setCategories] = useState([]);
  const [sources, setSources] = useState([]);
  const [months, setMonths] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editId, setEditId] = useState(null);
  const [editAmount, setEditAmount] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [lineItems, setLineItems] = useState({});
  const [loadingItems, setLoadingItems] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newTx, setNewTx] = useState({ date: new Date().toISOString().split('T')[0], vendor: '', amount: '', category: '', source: 'manual' });

  const load = () => {
    setLoading(true);
    api.getOrders(filters).then(orders => setData({ transactions: orders, total: orders.length }))
      .catch(console.error).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [filters]);
  useEffect(() => {
    // V2 stores replace the old categories/sources/months filters
    setCategories(['grocery', 'food', 'shopping', 'subscription', 'health', 'dental', 'other']);
    setSources(['Costco', 'Walmart']);
  }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    // V2: use importBill for file-based imports; manual adds not supported in v2 schema
    setShowAdd(false);
    setNewTx({ date: new Date().toISOString().split('T')[0], vendor: '', amount: '', category: '', source: 'manual' });
    load();
  };

  const handleSaveAmount = async (id) => {
    // V2: amounts are stored per order_item; order-level edits not supported
    setEditId(null); load();
  };

  const handleDelete = async (id) => {
    // V2: deletion not exposed in current API
    load();
  };

  const toggleExpand = async (id) => {
    if (expandedId === id) { setExpandedId(null); return; }
    setExpandedId(id);
    if (!lineItems[id]) {
      setLoadingItems(true);
      try {
        const items = await api.getOrderItems(id);
        setLineItems(prev => ({ ...prev, [id]: items }));
      } catch (err) { console.error(err); }
      setLoadingItems(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Filters bar */}
      <Card>
        <CardContent className="pt-4 pb-4">
          <div className="flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-48">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search vendors..." aria-label="Search vendors" className="pl-9" value={filters.search}
                onChange={e => setFilters(f => ({ ...f, search: e.target.value }))} />
            </div>
            <Select value={filters.category || 'all'} onValueChange={v => setFilters(f => ({ ...f, category: v === 'all' ? '' : v }))}>
              <SelectTrigger className="w-40" aria-label="Filter by category"><SelectValue placeholder="Category" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Categories</SelectItem>
                {categories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={filters.source || 'all'} onValueChange={v => setFilters(f => ({ ...f, source: v === 'all' ? '' : v }))}>
              <SelectTrigger className="w-36" aria-label="Filter by source"><SelectValue placeholder="Source" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Sources</SelectItem>
                {sources.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={filters.month || 'all'} onValueChange={v => setFilters(f => ({ ...f, month: v === 'all' ? '' : v }))}>
              <SelectTrigger className="w-36" aria-label="Filter by month"><SelectValue placeholder="Month" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Months</SelectItem>
                {months.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button onClick={() => setShowAdd(true)} className="ml-auto">
              <Plus size={16} /> Add
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{data.total} Transactions</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10"></TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Store / Service</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Source</TableHead>
                <TableHead className="w-20"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={7}><Skeleton className="h-5 w-full" /></TableCell>
                  </TableRow>
                ))
              ) : data.transactions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">
                    No transactions yet. Import bills or add manually.
                  </TableCell>
                </TableRow>
              ) : data.transactions.map(tx => (
                <Fragment key={tx.id}>
                  <TableRow className={expandedId === tx.id ? 'bg-muted/30' : ''}>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => toggleExpand(tx.id)}
                        aria-expanded={expandedId === tx.id}
                        aria-label={expandedId === tx.id ? "Hide itemized receipt" : "Show itemized receipt"}
                      >
                        {expandedId === tx.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                      </Button>
                    </TableCell>
                    <TableCell className="font-mono text-sm text-muted-foreground">{tx.date}</TableCell>
                    <TableCell className="font-medium">{tx.vendor}</TableCell>
                    <TableCell>
                      <Badge variant={CATEGORY_VARIANT[tx.category] || 'other'}>{tx.category}</Badge>
                    </TableCell>
                    <TableCell>
                      {editId === tx.id ? (
                        <div className="flex items-center gap-1.5">
                          <Input type="number" step="0.01" value={editAmount} autoFocus
                            onChange={e => setEditAmount(e.target.value)} className="w-24 h-7 text-xs" aria-label="Edit amount value" />
                          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => handleSaveAmount(tx.id)} aria-label="Save amount">
                            <Check size={13} />
                          </Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setEditId(null)} aria-label="Cancel editing">
                            <X size={13} />
                          </Button>
                        </div>
                      ) : (
                        <span className={tx.amount == null ? 'text-muted-foreground italic text-xs' : 'font-mono font-medium'}>
                          {tx.amount != null ? `$${tx.amount.toFixed(2)}` : 'unknown'}
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs font-normal">{tx.source}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        {tx.amount == null && (
                          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditId(tx.id); setEditAmount(''); }} aria-label="Edit amount">
                            <Pencil size={13} />
                          </Button>
                        )}
                        <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => handleDelete(tx.id)} aria-label={`Delete transaction with ${tx.vendor}`}>
                          <Trash2 size={13} />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>

                  {/* Line items expanded row */}
                  {expandedId === tx.id && (
                    <TableRow className="bg-muted/20 hover:bg-muted/20">
                      <TableCell></TableCell>
                      <TableCell colSpan={6} className="pb-4 pt-0">
                        <div className="mt-2 rounded-lg border bg-card p-4">
                          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground mb-3">
                            <FileText size={14} /> Itemized Receipt
                          </div>
                          {loadingItems && !lineItems[tx.id] ? (
                            <Skeleton className="h-10 w-full" />
                          ) : lineItems[tx.id]?.length > 0 ? (
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b text-xs text-muted-foreground">
                                  <th className="pb-2 text-left font-medium">Product</th>
                                  <th className="pb-2 text-right font-medium">Qty</th>
                                  <th className="pb-2 text-right font-medium">Price</th>
                                  <th className="pb-2 text-right font-medium">Total</th>
                                </tr>
                              </thead>
                              <tbody>
                                {lineItems[tx.id].map(item => (
                                  <tr key={item.id} className="border-b border-muted last:border-0">
                                    <td className="py-2 text-foreground">
                                      {item.product_name}
                                      {item.discount > 0 && (
                                        <span className="ml-2 text-xs text-emerald-600">−${item.discount.toFixed(2)}</span>
                                      )}
                                    </td>
                                    <td className="py-2 text-right text-muted-foreground">{item.quantity}</td>
                                    <td className="py-2 text-right text-muted-foreground font-mono">
                                      {item.unit_price ? `$${item.unit_price.toFixed(2)}` : '—'}
                                    </td>
                                    <td className="py-2 text-right font-mono font-medium">
                                      {item.total_price ? `$${item.total_price.toFixed(2)}` : '—'}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            <div className="flex items-center gap-2 text-muted-foreground text-sm py-2">
                              <Package size={14} /> No item details available for this transaction.
                            </div>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Add Transaction Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Transaction</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAdd} className="space-y-4 mt-2">
            <div className="space-y-1.5">
              <label htmlFor="new-tx-date" className="text-sm font-medium">Date</label>
              <Input id="new-tx-date" type="date" value={newTx.date} onChange={e => setNewTx(t => ({ ...t, date: e.target.value }))} required />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="new-tx-vendor" className="text-sm font-medium">Vendor / Store</label>
              <Input id="new-tx-vendor" placeholder="e.g. Walmart, DoorDash" value={newTx.vendor} onChange={e => setNewTx(t => ({ ...t, vendor: e.target.value }))} required />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="new-tx-amount" className="text-sm font-medium">Amount ($)</label>
              <Input id="new-tx-amount" type="number" step="0.01" placeholder="Leave blank if unknown" value={newTx.amount} onChange={e => setNewTx(t => ({ ...t, amount: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="new-tx-category" className="text-sm font-medium">Category</label>
              <Select value={newTx.category || 'auto'} onValueChange={v => setNewTx(t => ({ ...t, category: v === 'auto' ? '' : v }))}>
                <SelectTrigger id="new-tx-category"><SelectValue placeholder="Auto-detect" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto-detect</SelectItem>
                  {CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button type="submit">Add Transaction</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
