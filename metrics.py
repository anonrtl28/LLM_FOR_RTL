#!/usr/bin/env python3
"""
Metrics calculation for LLM-based RTL generation evaluation
Based on the formulas from the research paper

Notation:
- N = number of designs
- p_i = 1 if Port Signature passes, else 0
- c_i = 1 if Compile passes, else 0
- e_i = 1 if Elaboration passes, else 0
- m_i = 1 if Module Completeness passes, else 0
- q_i = 1 if Functional Equivalence passes, else 0
- y_i = p_i * c_i * e_i * m_i * q_i (end-to-end success on first attempt)
- y_i^(a) = end-to-end success on attempt a
- A_i = first successful attempt (if any)
- t_i = time to first successful pass
- K = refinement budget (default 3)
"""

import csv
import sys

# =====================================
# CONFIGURATION
# =====================================
K = 3  # Refinement budget
file_name = "results.csv"
if len(sys.argv) > 1:
    file_name = sys.argv[1]

# =====================================
# LOAD DATA
# =====================================
with open(file_name, 'r') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

N = len(rows)

if N == 0:
    print("No data found")
    sys.exit(1)

print(f"\n{'='*60}")
print(f"LLM RTL GENERATION - METRICS REPORT")
print(f"{'='*60}")
print(f"Number of designs (N): {N}")
print(f"Refinement budget (K): {K}")
print(f"{'='*60}")

# =====================================
# COLLECT DATA FROM CSV
# =====================================
# The CSV should have columns: design, P, C, E, M, F, S, A_i, TTFP, SEY@K, Refinements, First_Failure, Root_Cause

p_list = []  # p_i for each design
c_list = []  # c_i for each design
e_list = []  # e_i for each design
m_list = []  # m_i for each design
q_list = []  # q_i for each design (called F in CSV)
A_list = []  # A_i (first successful attempt)
t_list = []  # t_i (time to first pass)
sey_list = []  # SEY@K per design
first_failure_list = []  # First failure stage
root_cause_list = []  # Root cause classification

for row in rows:
    p_list.append(1 if row['P'] == 'PASS' else 0)
    c_list.append(1 if row['C'] == 'PASS' else 0)
    e_list.append(1 if row['E'] == 'PASS' else 0)
    m_list.append(1 if row['M'] == 'PASS' else 0)
    q_list.append(1 if row['F'] == 'PASS' else 0)
    A_list.append(int(row['A_i']))
    t_list.append(float(row['TTFP']))
    sey_list.append(int(row['SEY@K']))
    first_failure_list.append(row.get('First_Failure', 'None'))
    root_cause_list.append(row.get('Root_Cause', 'other'))

# =====================================
# SECTION 4.1 - Notation (summaries)
# =====================================
sum_p = sum(p_list)
sum_c = sum(c_list)
sum_e = sum(e_list)
sum_m = sum(m_list)
sum_q = sum(q_list)

print(f"\n{'='*60}")
print("SECTION 4.1 - Notation (Summary)")
print(f"{'='*60}")
print(f"∑p_i (Port Signature passes): {sum_p}/{N}")
print(f"∑c_i (Compile passes):        {sum_c}/{N}")
print(f"∑e_i (Elaboration passes):    {sum_e}/{N}")
print(f"∑m_i (Module Completeness):   {sum_m}/{N}")
print(f"∑q_i (Functional Eq passes):  {sum_q}/{N}")

# =====================================
# SECTION 4.2.1 - Stage-wise Pass Rates
# =====================================
PPS = sum_p / N
CR = sum_c / N
ER = sum_e / N
MC = sum_m / N
FE = sum_q / N

print(f"\n{'='*60}")
print("SECTION 4.2.1 - Stage-wise Pass Rates")
print(f"{'='*60}")
print(f"PPS (Port Signature):  {PPS:.3f} ({sum_p}/{N})")
print(f"CR  (Compile):         {CR:.3f} ({sum_c}/{N})")
print(f"ER  (Elaboration):     {ER:.3f} ({sum_e}/{N})")
print(f"MC  (Module Complete): {MC:.3f} ({sum_m}/{N})")
print(f"FE  (Functional Eq):   {FE:.3f} ({sum_q}/{N})")

# =====================================
# SECTION 4.2.2 - Conditional Yields
# =====================================
def safe_div(a, b):
    return a / max(1, b)

CR_given_PPS = safe_div(sum_c, sum_p)
ER_given_CR = safe_div(sum_e, sum_c)
MC_given_ER = safe_div(sum_m, sum_e)
FE_given_MC = safe_div(sum_q, sum_m)

print(f"\n{'='*60}")
print("SECTION 4.2.2 - Conditional Yields")
print(f"{'='*60}")
print(f"CR | PPS = {CR_given_PPS:.3f}  (Compile given Port Signature)")
print(f"ER | CR  = {ER_given_CR:.3f}  (Elaboration given Compile)")
print(f"MC | ER  = {MC_given_ER:.3f}  (Module Complete given Elaboration)")
print(f"FE | MC  = {FE_given_MC:.3f}  (Functional Eq given Module Complete)")

print(f"\n  Interpretation:")
print(f"  - Low CR|PPS: fragile syntax or interface handling")
print(f"  - Low ER|CR:  hierarchy or parameter problems")
print(f"  - Low MC|ER:  structurally incomplete RTL")
print(f"  - Low FE|MC:  functional mismatch against baseline")

# =====================================
# SECTION 4.2.3 - Bounded Refinement and Effort (E2E@K)
# =====================================
# E2E@K = (1/N) * sum( max(y_i^(a)) for a=1..K )
# where y_i^(a) = p_i^(a) * c_i^(a) * e_i^(a) * m_i^(a) * q_i^(a)
# Since we track A_i as first successful attempt, success if A_i <= K
e2e_at_K = sum(1 for a in A_list if a <= K) / N

print(f"\n{'='*60}")
print("SECTION 4.2.3 - Bounded Refinement and Effort (E2E@K)")
print(f"{'='*60}")
print(f"E2E@{K} = {e2e_at_K:.3f}  (End-to-end success within {K} attempts)")

# =====================================
# SECTION 4.2.4 - Failure Breakdown
# =====================================
print(f"\n{'='*60}")
print("SECTION 4.2.4 - Failure Breakdown")
print(f"{'='*60}")

# 4.2.4 (1) - First-failure stage
print("\n(1) First-failure stage distribution:")
fail_stages = {'P': 0, 'C': 0, 'E': 0, 'M': 0, 'F': 0, 'S': 0, 'None': 0}
for ff in first_failure_list:
    stage = ff.replace('-stage', '') if ff != 'None' else 'None'
    fail_stages[stage] = fail_stages.get(stage, 0) + 1

for stage in ['P', 'C', 'E', 'M', 'F', 'S', 'None']:
    count = fail_stages.get(stage, 0)
    if count > 0:
        print(f"  {stage:4s}: {count:2d} design(s) ({count/N:.1%})")

# 4.2.4 (2) - Root-cause taxonomy
print("\n(2) Root-cause taxonomy shares:")
root_cause_counts = {'compiler': 0, 'not-elaborated': 0, 'partial_module': 0, 'functional_mismatch': 0, 'other': 0}
for rc in root_cause_list:
    if rc in root_cause_counts:
        root_cause_counts[rc] += 1
    else:
        root_cause_counts['other'] += 1

total_failures = sum(v for k, v in root_cause_counts.items() if k != 'other')  # Designs that actually failed
total_all = sum(root_cause_counts.values())

print(f"  Total failures: {total_failures} designs")
for cause in ['compiler', 'not-elaborated', 'partial_module', 'functional_mismatch', 'other']:
    count = root_cause_counts.get(cause, 0)
    if count > 0:
        share = count / total_failures if total_failures > 0 else 0
        print(f"  {cause:18s}: {share:.1%} ({count} failures)")

# =====================================
# SECTION 4.2.5 - Synthesis-Eligible Yield (SEY@K)
# =====================================
# SEY@K = (1/N) * sum( max(c_i^(a) * e_i^(a)) for a=1..K )
sey_at_K = sum(sey_list) / N

print(f"\n{'='*60}")
print("SECTION 4.2.5 - Synthesis-Eligible Yield (SEY@K)")
print(f"{'='*60}")
print(f"SEY@{K} = {sey_at_K:.3f}  (Synthesis-eligible within {K} attempts)")
print(f"  Note: A design is synthesis-eligible if it compiles AND elaborates")

# =====================================
# AUXILIARY METRICS (from Section 4.3)
# =====================================
print(f"\n{'='*60}")
print("AUXILIARY METRICS (Section 4.3)")
print(f"{'='*60}")

# One-shot end-to-end rate (E2E@1)
# E2E@1 = (1/N) * sum(y_i) where y_i = p_i * c_i * e_i * m_i * q_i on first attempt
y_i_list = [p_list[i] * c_list[i] * e_list[i] * m_list[i] * q_list[i] for i in range(N)]
e2e_at_1 = sum(y_i_list) / N

print(f"\nE2E@1 (One-shot end-to-end rate): {e2e_at_1:.3f}")

# Edits to Success (ETS) and Time to First Pass (TTFP)
# Only for solved designs (A_i <= K)
solved_indices = [i for i, a in enumerate(A_list) if a <= K]

if solved_indices:
    # ETS = (1/|S|) * sum(A_i - 1)
    ETS = sum(A_list[i] - 1 for i in solved_indices) / len(solved_indices)
    
    # TTFP = (1/|S|) * sum(t_i)
    TTFP = sum(t_list[i] for i in solved_indices) / len(solved_indices)
    
    print(f"\nEdits to Success (ETS):  {ETS:.3f}  (avg refinements before success)")
    print(f"Time to First Pass (TTFP): {TTFP:.2f} seconds")
    print(f"  Solved designs: {len(solved_indices)}/{N}")
else:
    print("\nETS and TTFP: No solved designs within K attempts")

# =====================================
# COMPLETE SUMMARY TABLE
# =====================================
print(f"\n{'='*60}")
print("COMPLETE SUMMARY TABLE")
print(f"{'='*60}")

print(f"\n{'Metric':<25} {'Value':<15} {'Formula'}")
print(f"{'-'*60}")

print(f"{'PPS (Port Signature)':<25} {PPS:.3f} {'':<15} (1/N)*∑p_i")
print(f"{'CR (Compile)':<25} {CR:.3f} {'':<15} (1/N)*∑c_i")
print(f"{'ER (Elaboration)':<25} {ER:.3f} {'':<15} (1/N)*∑e_i")
print(f"{'MC (Module Complete)':<25} {MC:.3f} {'':<15} (1/N)*∑m_i")
print(f"{'FE (Functional Eq)':<25} {FE:.3f} {'':<15} (1/N)*∑q_i")
print(f"{'-'*60}")
print(f"{'CR | PPS':<25} {CR_given_PPS:.3f} {'':<15} ∑c_i/max(1,∑p_i)")
print(f"{'ER | CR':<25} {ER_given_CR:.3f} {'':<15} ∑e_i/max(1,∑c_i)")
print(f"{'MC | ER':<25} {MC_given_ER:.3f} {'':<15} ∑m_i/max(1,∑e_i)")
print(f"{'FE | MC':<25} {FE_given_MC:.3f} {'':<15} ∑q_i/max(1,∑m_i)")
print(f"{'-'*60}")
print(f"{'E2E@1 (One-shot)':<25} {e2e_at_1:.3f} {'':<15} (1/N)*∑y_i")
print(f"{'E2E@' + str(K):<25} {e2e_at_K:.3f} {'':<15} (1/N)*∑max(y_i^(a))")
print(f"{'SEY@' + str(K):<25} {sey_at_K:.3f} {'':<15} (1/N)*∑max(c_i^(a)*e_i^(a))")
if solved_indices:
    print(f"{'-'*60}")
    print(f"{'ETS':<25} {ETS:.3f} {'':<15} (1/|S|)*∑(A_i-1)")
    print(f"{'TTFP':<25} {TTFP:.2f}s {'':<15} (1/|S|)*∑t_i")

# =====================================
# SAVE REPORT TO FILE
# =====================================
with open("metrics_report.txt", "w") as report:
    report.write("="*60 + "\n")
    report.write("LLM RTL GENERATION - METRICS REPORT\n")
    report.write("="*60 + "\n\n")
    
    report.write(f"Number of designs (N): {N}\n")
    report.write(f"Refinement budget (K): {K}\n\n")
    
    report.write("Stage-wise Pass Rates (4.2.1):\n")
    report.write(f"  PPS: {PPS:.3f}\n")
    report.write(f"  CR:  {CR:.3f}\n")
    report.write(f"  ER:  {ER:.3f}\n")
    report.write(f"  MC:  {MC:.3f}\n")
    report.write(f"  FE:  {FE:.3f}\n\n")
    
    report.write("Conditional Yields (4.2.2):\n")
    report.write(f"  CR | PPS: {CR_given_PPS:.3f}\n")
    report.write(f"  ER | CR:  {ER_given_CR:.3f}\n")
    report.write(f"  MC | ER:  {MC_given_ER:.3f}\n")
    report.write(f"  FE | MC:  {FE_given_MC:.3f}\n\n")
    
    report.write("End-to-End Metrics (4.2.3 & 4.2.5):\n")
    report.write(f"  E2E@1: {e2e_at_1:.3f}\n")
    report.write(f"  E2E@{K}: {e2e_at_K:.3f}\n")
    report.write(f"  SEY@{K}: {sey_at_K:.3f}\n\n")
    
    if solved_indices:
        report.write("Effort Metrics (4.3):\n")
        report.write(f"  ETS:  {ETS:.3f}\n")
        report.write(f"  TTFP: {TTFP:.2f} seconds\n\n")
    
    report.write("Failure Breakdown (4.2.4):\n")
    report.write("  First-failure stage distribution:\n")
    for stage in ['P', 'C', 'E', 'M', 'F', 'S']:
        if fail_stages.get(stage, 0) > 0:
            report.write(f"    {stage}: {fail_stages[stage]} ({fail_stages[stage]/N:.1%})\n")
    if fail_stages.get('None', 0) > 0:
        report.write(f"    No failure: {fail_stages['None']}\n")
    
    report.write("\n  Root-cause taxonomy shares:\n")
    for cause in ['compiler', 'not-elaborated', 'partial_module', 'functional_mismatch']:
        count = root_cause_counts.get(cause, 0)
        if count > 0:
            share = count / total_failures if total_failures > 0 else 0
            report.write(f"    {cause}: {share:.1%} ({count} failures)\n")

print(f"\n{'='*60}")
print(f"✅ Metrics report saved to: metrics_report.txt")
print(f"{'='*60}")
