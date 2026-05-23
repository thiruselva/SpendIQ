import sqlite3
import re

def clean_tokens(name):
    name = name.lower()
    # remove sizes/units
    name = re.sub(r'\b\d+(?:\.\d+)?\s*(?:oz|lb|ct|pk|pack|count|g|kg|ml|liter|each|loads|qt|pt|gal|gallon|bunch|bag)\b', '', name)
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    tokens = set(t for t in name.split() if len(t) > 2 and t not in [
        'organic', 'fresh', 'great', 'value', 'member', 'mark', 
        'kirkland', 'signature', 'choice', 'brand', 'selection',
        'marketside', 'guaranteed'
    ])
    return tokens

def main():
    conn = sqlite3.connect('backend/data/spendiq_v2.db')
    conn.row_factory = sqlite3.Row
    
    walmart = conn.execute('SELECT id, canonical_name FROM products WHERE id < 600').fetchall()
    costco = conn.execute('SELECT id, canonical_name FROM products WHERE id >= 600').fetchall()
    
    print(f"Walmart products: {len(walmart)}, Costco products: {len(costco)}")
    
    matches = []
    for c in costco:
        c_toks = clean_tokens(c['canonical_name'])
        if not c_toks:
            continue
        for w in walmart:
            w_toks = clean_tokens(w['canonical_name'])
            if not w_toks:
                continue
            intersection = c_toks.intersection(w_toks)
            
            # Match if:
            # 1. They have exact same clean tokens
            # 2. Or they have at least 2 tokens overlap (for multi-word products)
            # 3. Or they overlap 100% on the shorter token list (e.g. "red grapes" and "grapes")
            is_match = False
            if c_toks == w_toks:
                is_match = True
            elif len(intersection) >= 2:
                is_match = True
            elif len(intersection) >= 1 and (len(c_toks) == 1 or len(w_toks) == 1) and intersection == (c_toks if len(c_toks) == 1 else w_toks):
                is_match = True
                
            if is_match:
                matches.append((c['canonical_name'], w['canonical_name'], c['id'], w['id']))
                
    print(f"Found {len(matches)} potential matches:")
    for m in sorted(matches, key=lambda x: x[0])[:100]:
        print(f"  Costco: {m[0]:30s} <---> Walmart: {m[1]} (Costco ID: {m[2]} -> Walmart ID: {m[3]})")
        
    conn.close()

if __name__ == "__main__":
    main()
