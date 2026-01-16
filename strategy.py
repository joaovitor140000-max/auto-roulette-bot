import statistics

def classify_columns(numbers):
    cols = {1: 0, 2: 0, 3: 0}
    for n in numbers:
        if n == 0:
            continue
        col = n % 3 if n % 3 != 0 else 3
        cols[col] += 1
    return cols

def confidence_level(cols):
    total = sum(cols.values())
    if total == 0:
        return 0
    return max(cols.values()) / total

def roulette_stability(numbers):
    if len(numbers) < 10:
        return "instavel"
    std = statistics.stdev(numbers)
    if std < 11:
        return "quente"
    elif std < 14:
        return "neutra"
    return "instavel"
