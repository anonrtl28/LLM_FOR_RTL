import csv
import time
import subprocess
import json
import os
import shutil
import re

# =====================================
# CONFIG
# =====================================
DESIGNS = [
    "half_adder",
    "priority_encoder",
    "ripple_carry_adder"
] # edit the list based on the designs you want to test; ensure that prompts and the reference designs are available under the respective directory

LLM_PROVIDER = "ollama"
K = 3  # Refinement budget
INTERACTIVE_MODE = True  # Set to False to run without prompts

# Create directories
os.makedirs("logs", exist_ok=True)
os.makedirs("prompts_backup", exist_ok=True)

# =====================================
# DATA STORAGE FOR METRICS
# =====================================
design_success_data = {}  # Store success data per design

# =====================================
# PROMPT REVIEW FUNCTION
# =====================================
def review_and_edit_prompt(design):
    """Allow user to review and edit prompt before running"""
    prompt_file = f"prompts/{design}.txt"

    if not os.path.exists(prompt_file):
        print(f"  [!] Prompt file not found: {prompt_file}")
        return False

    print(f"\n  📝 Current prompt for {design}:")
    print("  " + "-"*40)
    with open(prompt_file, "r") as f:
        lines = f.read().split('\n')
        for line in lines[:10]:
            print(f"  {line[:80]}")
        if len(lines) > 10:
            print(f"  ... ({len(lines)-10} more lines)")
    print("  " + "-"*40)

    while True:
        choice = input(f"\n  [e] Edit | [v] View all | [c] Continue | [s] Skip: ").lower()

        if choice == 'e':
            editor = os.environ.get('EDITOR', 'nano')
            subprocess.call([editor, prompt_file])
            print("  ✓ Prompt updated")
            return True
        elif choice == 'v':
            print(f"\n  Full prompt for {design}:")
            print("="*60)
            with open(prompt_file, "r") as f:
                print(f.read())
            print("="*60)
        elif choice == 'c':
            return True
        elif choice == 's':
            return False
        else:
            print("  Invalid choice")

# =====================================
# PROMPT REFINEMENT
# =====================================
def refine_prompt(design, error_stage, error_msg, generated_rtl, attempt):
    """Refine prompt based on failure"""
    prompt_file = f"prompts/{design}.txt"

    with open(prompt_file, "r") as f:
        original = f.read()

    refined = f"""{original}

[FEEDBACK FROM PREVIOUS FAILURE - Attempt {attempt}]
Stage that failed: {error_stage}
Error: {error_msg}

The generated code had issues. Please fix the Verilog code:
- All ports must have direction (input/output)
- Use 'assign' statements for combinational logic
- Do NOT use 'reg' for simple combinational outputs
- Module and endmodule must be properly matched
- No parameters unless specified
- Output ONLY the Verilog code, no explanations

Provide corrected Verilog code:
"""

    with open(prompt_file, "w") as f:
        f.write(refined)

    print(f"  ✓ Prompt refined based on {error_stage} failure")

# =====================================
# BACKUP/RESTORE PROMPTS
# =====================================
def backup_prompt(design):
    src = f"prompts/{design}.txt"
    dst = f"prompts_backup/{design}_original.txt"
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy(src, dst)
        print(f"  📁 Backed up: {src}")

def restore_prompt(design):
    src = f"prompts_backup/{design}_original.txt"
    dst = f"prompts/{design}.txt"
    if os.path.exists(src):
        shutil.copy(src, dst)
        print(f"  📁 Restored original prompt for {design}")

# =====================================
# CLASSIFY ROOT CAUSE
# =====================================
def classify_root_cause(error_stage, error_msg):
    """
    Classify failure into one of four categories:
    - compiler: syntax or static legality errors (C-stage)
    - not-elaborated: hierarchy, parameter, or generate issues (E-stage)
    - partial_module: compiles but incomplete logic (P-stage, M-stage)
    - functional_mismatch: not equivalent to reference RTL (F-stage)
    """
    if error_stage == 'C-stage':
        return 'compiler'
    elif error_stage == 'E-stage':
        return 'not-elaborated'
    elif error_stage in ['P-stage', 'M-stage']:
        return 'partial_module'
    elif error_stage == 'F-stage':
        return 'functional_mismatch'
    else:
        return 'other'

# =====================================
# PARSE OUTPUT
# =====================================
def parse_output(output):
    """Extract JSON and error info from output"""
    json_match = None
    error_stage = None
    error_msg = None
    generated_rtl = None

    # Find JSON (between __JSON_START__ and __JSON_END__ or just as single line)
    in_json = False
    for line in output.split('\n'):
        line = line.strip()
        if line == '__JSON_START__':
            in_json = True
            continue
        elif line == '__JSON_END__':
            break
        elif in_json and line.startswith('{') and line.endswith('}'):
            try:
                json_match = json.loads(line)
            except:
                pass
        elif not in_json and line.startswith('{') and line.endswith('}'):
            try:
                json_match = json.loads(line)
            except:
                pass

    # Find error stage
    if 'P-stage FAILED' in output:
        error_stage = 'P-stage'
        match = re.search(r'Issues: (\[.*?\])', output)
        error_msg = match.group(1) if match else 'Port signature check failed'
    elif 'C-stage FAILED' in output:
        error_stage = 'C-stage'
        error_msg = 'Iverilog syntax check failed'
    elif 'M-stage FAILED' in output:
        error_stage = 'M-stage'
        match = re.search(r'Issues: (\[.*?\])', output)
        error_msg = match.group(1) if match else 'Module quality check failed'
    elif 'E-stage FAILED' in output:
        error_stage = 'E-stage'
        error_msg = 'Yosys elaboration failed'
    elif 'F-stage FAILED' in output:
        error_stage = 'F-stage'
        error_msg = 'Formal equivalence failed'
    elif 'S-stage FAILED' in output:
        error_stage = 'S-stage'
        error_msg = 'Remote synthesis failed'

    # Get generated RTL for feedback
    try:
        with open("rtl/raw_output.txt", "r") as f:
            generated_rtl = f.read()[:500]
    except:
        pass

    return json_match, error_stage, error_msg, generated_rtl

# =====================================
# UPDATE MAIN.PY
# =====================================
def update_main_py(design, provider):
    """Update DESIGN and LLM_PROVIDER in main.py"""
    with open("main.py", "r") as f:
        lines = f.readlines()
    with open("main.py", "w") as f:
        for line in lines:
            if line.startswith("DESIGN"):
                f.write(f'DESIGN = "{design}"\n')
            elif line.startswith("LLM_PROVIDER"):
                f.write(f'LLM_PROVIDER = "{provider}"\n')
            else:
                f.write(line)

# =====================================
# MAIN LOOP
# =====================================
def main():
    print(f"\n{'='*60}")
    print("LLM RTL Generation Test Suite")
    print(f"{'='*60}")
    print(f"Designs: {', '.join(DESIGNS)}")
    print(f"LLM Provider: {LLM_PROVIDER}")
    print(f"Refinement budget (K): {K}")
    print(f"Interactive mode: {'ON' if INTERACTIVE_MODE else 'OFF'}")
    print(f"{'='*60}")

    with open("results.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "design", "P", "C", "E", "M", "F", "S",
            "A_i", "TTFP", "SEY@K", "Refinements",
            "First_Failure", "Root_Cause"
        ])

        for design in DESIGNS:
            print(f"\n{'='*50}")
            print(f"📁 Testing: {design}")
            print(f"{'='*50}")

            # Interactive prompt review
            if INTERACTIVE_MODE:
                if not review_and_edit_prompt(design):
                    print(f"  ⏭️ Skipping {design}")
                    continue

            # Backup original prompt
            backup_prompt(design)

            # Initialize design data
            design_data = {
                'attempts': [],
                'success_attempt': None,
                'time_to_success': None,
                'first_failure_stage': None,
                'root_cause': None
            }

            success = False
            sey_success = False
            first_pass = None
            time_to_first = None
            total_time = 0
            final_res = None
            refinements = 0
            first_failure_stage = None
            root_cause = None

            for attempt in range(1, K + 1):
                print(f"\n--- Attempt {attempt}/{K} ---")
                if attempt > 1:
                    print(f"  🔄 Using refined prompt")

                # Update main.py
                update_main_py(design, LLM_PROVIDER)

                start = time.time()

                # Run main.py with real-time output
                process = subprocess.Popen(
                    ["python3", "main.py"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                output_lines = []
                for line in process.stdout:
                    print(line, end='')
                    output_lines.append(line)

                process.wait()
                end = time.time()
                attempt_time = end - start
                total_time += attempt_time
                full_output = ''.join(output_lines)

                # Parse output
                res, error_stage, error_msg, generated_rtl = parse_output(full_output)

                if res:
                    # Store attempt data
                    attempt_data = {
                        'attempt': attempt,
                        'p': 1 if res.get('P') == 'PASS' else 0,
                        'c': 1 if res.get('C') == 'PASS' else 0,
                        'e': 1 if res.get('E') == 'PASS' else 0,
                        'm': 1 if res.get('M') == 'PASS' else 0,
                        'q': 1 if res.get('F') == 'PASS' else 0,
                        's': 1 if res.get('S') == 'PASS' else 0,
                        'time': attempt_time
                    }
                    design_data['attempts'].append(attempt_data)
                    final_res = res
                    
                    print(f"\n  📊 Results: P={res.get('P')}, C={res.get('C')}, E={res.get('E')}, M={res.get('M')}, F={res.get('F')}, S={res.get('S')}")
                else:
                    print("  ⚠️ Could not parse JSON")
                    continue

                # Track first failure (only first failing attempt)
                if not success and first_failure_stage is None and not all([
                    res.get("P") == "PASS",
                    res.get("C") == "PASS",
                    res.get("E") == "PASS",
                    res.get("M") == "PASS",
                    res.get("F") == "PASS"
                ]):
                    if error_stage:
                        first_failure_stage = error_stage
                        root_cause = classify_root_cause(error_stage, error_msg)
                        print(f"  📌 First failure at: {first_failure_stage}")
                        print(f"  📌 Root cause: {root_cause}")

                # Check SEY@K (synthesis-eligible: C and E pass)
                if res.get("C") == "PASS" and res.get("E") == "PASS":
                    sey_success = True

                # Check full success (all front-end stages pass)
                if all([
                    res.get("P") == "PASS",
                    res.get("C") == "PASS",
                    res.get("E") == "PASS",
                    res.get("M") == "PASS",
                    res.get("F") == "PASS"
                ]):
                    print(f"\n  ✅ SUCCESS on attempt {attempt}!")
                    success = True
                    first_pass = attempt
                    time_to_first = total_time
                    design_data['success_attempt'] = attempt
                    design_data['time_to_success'] = total_time
                    break
                else:
                    print("  ❌ Failed")
                    
                    # Refine prompt for next attempt
                    if attempt < K and error_stage:
                        refinements += 1
                        refine_prompt(design, error_stage, error_msg, generated_rtl, attempt)

            # Store design data
            design_data['first_failure_stage'] = first_failure_stage
            design_data['root_cause'] = root_cause
            design_success_data[design] = design_data

            # Restore original prompt
            restore_prompt(design)

            # Handle failures (if no result was parsed)
            if final_res is None:
                final_res = {
                    "P": "FAIL", "C": "FAIL", "E": "FAIL",
                    "M": "FAIL", "F": "FAIL", "S": "FAIL"
                }

            # Write to CSV
            writer.writerow([
                design,
                final_res.get("P", "FAIL"),
                final_res.get("C", "FAIL"),
                final_res.get("E", "FAIL"),
                final_res.get("M", "FAIL"),
                final_res.get("F", "FAIL"),
                final_res.get("S", "FAIL"),
                first_pass if first_pass else K + 1,  # A_i = K+1 if never succeeded
                round(time_to_first if time_to_first else total_time, 3),  # TTFP
                1 if sey_success else 0,  # SEY@K
                refinements,
                first_failure_stage if first_failure_stage else "None",
                root_cause if root_cause else "None"
            ])
            
            # Print summary for this design
            print(f"\n  📈 {design} summary:")
            print(f"     Success: {'Yes' if success else 'No'}")
            print(f"     Attempts to success: {first_pass if first_pass else 'N/A'}")
            print(f"     First failure: {first_failure_stage if first_failure_stage else 'None'}")
            print(f"     Root cause: {root_cause if root_cause else 'None'}")

    print(f"\n{'='*60}")
    print("✅ results.csv generated!")
    print(f"{'='*60}")

    # Print preview of results
    print("\n📊 Results preview:")
    print("-"*80)
    with open("results.csv", "r") as f:
        for i, line in enumerate(f):
            if i == 0:
                print(f"  {line.strip()}")
            else:
                parts = line.strip().split(',')
                print(f"  {parts[0]}: P={parts[1]}, C={parts[2]}, E={parts[3]}, M={parts[4]}, F={parts[5]}, S={parts[6]}, A_i={parts[7]}, SEY={parts[9]}")
    print("-"*80)

if __name__ == "__main__":
    main()
