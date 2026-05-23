"""SpendIQ v2 Intelligence Engine — Pattern computation, price comparison, shopping list generation."""
from .engine import IntelligenceEngine
from .patterns import compute_purchase_patterns, get_patterns_for_store
from .comparisons import compute_store_comparisons, generate_savings_tips
