import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import { LayoutDashboard, ArrowLeftRight, Lightbulb, ShoppingCart, Upload, TrendingUp, Menu, X } from 'lucide-react';
import Overview from './components/Overview';
import Transactions from './components/Transactions';
import Insights from './components/Insights';
import ShoppingList from './components/ShoppingList';
import Import from './components/Import';
import { cn } from '@/lib/utils';
import './index.css';

const NAV = [
  { to: '/',              icon: LayoutDashboard, label: 'Overview'     },
  { to: '/transactions',  icon: ArrowLeftRight,  label: 'Transactions' },
  { to: '/insights',      icon: Lightbulb,       label: 'Insights'     },
  { to: '/shopping',      icon: ShoppingCart,    label: 'Shopping List'},
  { to: '/import',        icon: Upload,          label: 'Import'       },
];

function Sidebar({ open, onClose }) {
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-20 bg-black/50 lg:hidden"
          onClick={onClose}
          role="presentation"
          aria-hidden="true"
        />
      )}

      <aside className={cn(
        'fixed top-0 left-0 z-30 h-full w-64 bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))] flex flex-col transition-transform duration-300',
        'lg:translate-x-0 lg:static lg:z-auto',
        open ? 'translate-x-0' : '-translate-x-full'
      )}>
        {/* Logo */}
        <div className="flex items-center gap-3 px-6 py-5 border-b border-white/10">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10">
            <TrendingUp size={20} className="text-white" />
          </div>
          <div>
            <p className="font-bold text-white text-base leading-tight">SpendIQ</p>
            <p className="text-white/50 text-xs">Smart spending tracker</p>
          </div>
          <button onClick={onClose} className="ml-auto lg:hidden text-white/60 hover:text-white" aria-label="Close sidebar">
            <X size={18} />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={onClose}
              className={({ isActive }) => cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-white/15 text-white'
                  : 'text-white/60 hover:bg-white/8 hover:text-white/90'
              )}
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-white/10">
          <p className="text-white/30 text-xs">© 2026 SpendIQ</p>
        </div>
      </aside>
    </>
  );
}

function Layout({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const page = NAV.find(n => n.to === location.pathname) || NAV[0];

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center gap-4 px-6 py-4 border-b bg-background/95 backdrop-blur">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden text-muted-foreground hover:text-foreground"
            aria-label="Open sidebar"
          >
            <Menu size={22} />
          </button>
          <h1 className="text-lg font-semibold">{page.label}</h1>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/"             element={<Overview />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/insights"     element={<Insights />} />
          <Route path="/shopping"     element={<ShoppingList />} />
          <Route path="/import"       element={<Import />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
