import csv
import sys

# =====================================
# INPUT FILE
# =====================================
# Default: results.csv
# Or pass file: python3 metrics.py results.csv

file_name = "results.csv"
if len(sys.argv) > 1:
    file_name = sys.argv[1]

# =====================================
# LOAD DATA
# =====================================
with open(file_name) as f:
    reader = csv.DictReader(f)
    rows = list(reader)

N = len(rows)

if N == 0:
    print("No data found")
    exit()

# =====================================
# INITIALIZE
# =====================================
P = C = E = M = F = S = 0

A = []          # A_i
T = []          # TTFP
SEY_list = []   # SEY@K

# =====================================
# COLLECT DATA
# =====================================
for row in rows:

    if row["P"] == "PASS": P += 1
    if row["C"] == "PASS": C += 1
    if row["E"] == "PASS": E += 1
    if row["M"] == "PASS": M += 1
    if row["F"] == "PASS": F += 1
    if row["S"] == "PASS": S += 1

    A.append(int(row["A_i"]))
    T.append(float(row["TTFP"]))
    SEY_list.append(int(row["SEY@K"]))

# =====================================
# 4.2.1 STAGE-WISE PASS RATES
# =====================================
print("\n=== Stage-wise Pass Rates ===")
print("PPS =", round(P/N, 3))
print("CR  =", round(C/N, 3))
print("ER  =", round(E/N, 3))
print("MC  =", round(M/N, 3))
print("FE  =", round(F/N, 3))

# =====================================
# 4.2.2 CONDITIONAL YIELDS
# =====================================
def safe_div(a, b):
    return round(a / max(1, b), 3)

print("\n=== Conditional Yields ===")
print("CR | PPS =", safe_div(C, P))
print("ER | CR  =", safe_div(E, C))
print("MC | ER  =", safe_div(M, E))
print("FE | MC  =", safe_div(F, M))

# =====================================
# 4.2.3 E2E@K
# =====================================
# success if A_i <= K (here K=3)
E2E = sum(1 for a in A if a <= 3) / N
print("\nE2E@K =", round(E2E, 3))

# =====================================
# 4.2.5 SEY@K
# =====================================
SEY = sum(SEY_list) / N
print("SEY@K =", round(SEY, 3))

# =====================================
# 4.3 AUXILIARY METRICS
# =====================================
S_idx = [i for i, a in enumerate(A) if a <= 3]

if len(S_idx) > 0:
    ETS = sum(A[i] - 1 for i in S_idx) / len(S_idx)
    TTFP_avg = sum(T[i] for i in S_idx) / len(S_idx)

    print("\nETS  =", round(ETS, 3))
    print("TTFP =", round(TTFP_avg, 3))
else:
    print("\nNo successful designs")

# =====================================
# 4.2.4 FIRST-FAILURE STAGE
# =====================================
print("\n=== First Failure Stage ===")

fail_counts = {"P":0, "C":0, "E":0, "M":0, "F":0}

for row in rows:
    if row["P"] != "PASS":
        fail_counts["P"] += 1
    elif row["C"] != "PASS":
        fail_counts["C"] += 1
    elif row["E"] != "PASS":
        fail_counts["E"] += 1
    elif row["M"] != "PASS":
        fail_counts["M"] += 1
    elif row["F"] != "PASS":
        fail_counts["F"] += 1

for k, v in fail_counts.items():
    print(k, "=", round(v / N, 3))
