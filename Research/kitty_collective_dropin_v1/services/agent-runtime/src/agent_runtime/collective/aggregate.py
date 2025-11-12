
from typing import List, Dict, Tuple

def score(item: Dict, weights: Tuple[float,float,float] = (0.6,0.3,0.1)) -> float:
    """
    Scoring function for council aggregation.
    item keys (optional): confidence [0..1], utility [0..1], risk [0..1]
    """
    conf = float(item.get("confidence", 0.5))
    util = float(item.get("utility", 0.5))
    risk = float(item.get("risk", 0.0))
    w_conf, w_util, w_risk = weights
    return w_conf * conf + w_util * util - w_risk * risk

def aggregate(items: List[Dict]) -> Dict:
    """
    Borda-like rank aggregation (simplified): sort by score and return best.
    """
    if not items:
        return {"answer": "", "confidence": 0.0, "utility": 0.0, "risk": 1.0}
    ranked = sorted(items, key=score, reverse=True)
    return ranked[0]
