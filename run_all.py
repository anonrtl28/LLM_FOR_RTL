import csv
import time
import subprocess
import json

# =====================================
# CONFIG
# =====================================
DESIGNS = [
    "half_adder",
    "priority_encoder",
    "ripple_carry_adder"
] #sample designs given, add all the designs that you want to test

LLM_PROVIDER = "openai"   # change if needed
K = 3 #refinement limit

# =====================================
# OUTPUT FILE
# =====================================
with open("results.csv", "w", newline="") as f:

    writer = csv.writer(f)

    writer.writerow([
        "design",
        "P","C","E","M","F","S",
        "A_i","TTFP","SEY@K"
    ])

    # =====================================
    # MAIN LOOP
    # =====================================
    for design in DESIGNS:

        print(f"\n=== {design} ===")

        success = False
        sey_success = False
        first_pass = None
        time_to_first = None

        total_time = 0
        final_res = None

        # =====================================
        # K ATTEMPTS
        # =====================================
        for attempt in range(1, K + 1):

            print(f"  Attempt {attempt}/{K}")

            # ---------------------------------
            # Update main.py (since hardcoded)
            # ---------------------------------
            with open("main.py", "r") as f:
                lines = f.readlines()

            with open("main.py", "w") as f:
                for line in lines:
                    if line.startswith("DESIGN"):
                        f.write(f'DESIGN = "{design}"\n')
                    elif line.startswith("LLM_PROVIDER"):
                        f.write(f'LLM_PROVIDER = "{LLM_PROVIDER}"\n')
                    else:
                        f.write(line)

            start = time.time()

            result = subprocess.run(
                ["python3", "main.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            end = time.time()
            total_time += (end - start)

            # ---------------------------------
            # Parse result (IMPORTANT)
            # main.py MUST print JSON before exit
            # ---------------------------------
            try:
                res = json.loads(result.stdout.strip().splitlines()[-1])
                final_res = res
            except:
                print("  [!] Could not parse output")
                print(result.stderr)
                continue

            # ---------------------------------
            # SEY@K → any attempt where C & E pass
            # ---------------------------------
            if res.get("C") == "PASS" and res.get("E") == "PASS":
                sey_success = True

            # ---------------------------------
            # FULL SUCCESS → all front-end stages
            # ---------------------------------
            if all([
                res.get("P") == "PASS",
                res.get("C") == "PASS",
                res.get("E") == "PASS",
                res.get("M") == "PASS",
                res.get("F") == "PASS"
            ]):
                print("  ✅ Success")

                success = True
                first_pass = attempt
                time_to_first = total_time
                break
            else:
                print("  ❌ Failed")

        # =====================================
        # HANDLE FAIL CASES
        # =====================================
        if final_res is None:
            final_res = {
                "P": "FAIL",
                "C": "FAIL",
                "E": "FAIL",
                "M": "FAIL",
                "F": "FAIL",
                "S": "FAIL"
            }

        if first_pass is None:
            first_pass = K + 1

        if time_to_first is None:
            time_to_first = total_time

        # =====================================
        # WRITE ROW
        # =====================================
        writer.writerow([
            design,
            final_res.get("P","FAIL"),
            final_res.get("C","FAIL"),
            final_res.get("E","FAIL"),
            final_res.get("M","FAIL"),
            final_res.get("F","FAIL"),
            final_res.get("S","FAIL"),
            first_pass,
            round(time_to_first, 3),
            1 if sey_success else 0
        ])

print("\nresults.csv generated")
