import os
import re
import sys
import time
import json
import requests
import subprocess

# =====================================
# INPUT
# =====================================
DESIGN = "half_adder"

# =====================================
# REFERENCE CONFIGURATION
# =====================================
# Specify the top module name in the reference files
# If None, it will use the same name as the generated RTL's top module
REFERENCE_TOP_NAME = None  # Example: "half_adder_golden" or "cpu_top_ref"

# =====================================
# LLM PROVIDER CONFIGURATION
# =====================================
LLM_PROVIDER = "ollama"

# --- OpenAI ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
OPENAI_MODEL   = "gpt-4o"

# --- Claude ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_API_KEY")
ANTHROPIC_MODEL   = "claude-3-5-sonnet-20241022"

# --- Gemini ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
GEMINI_MODEL   = "gemini-1.5-pro"

# --- DeepSeek ---
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_API_KEY")
DEEPSEEK_MODEL   = "deepseek-coder"

# --- HuggingFace ---
HF_API_KEY = os.environ.get("HF_API_KEY", "YOUR_HF_API_TOKEN")
HF_MODEL   = "shailja/fine-tuned-codegen-16B-Verilog"

# --- Ollama ---
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = "deepseek-coder:6.7b"

# =====================================
# FILE PATHS
# =====================================
PROMPT_FILE    = f"prompts/{DESIGN}.txt"
RTL_FILE       = f"rtl/{DESIGN}.v"
RAW_FILE       = f"rtl/raw_output.txt"
REFERENCE_PATH = f"reference/{DESIGN}"
RESULT_DIR     = f"results/{DESIGN}"

# =====================================
# SSH CONFIG
# =====================================
REMOTE_USER = "22bec0985"
REMOTE_HOST = "cadence.vit.ac.in"
REMOTE_DIR  = f"/home/userdata/{REMOTE_USER}/VAC2026/synthesis/{DESIGN}"
SSH_PASS    = "student"

os.makedirs("rtl", exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

start_time = time.time()

# =====================================
# RUN COMMAND
# =====================================
def run_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.returncode, result.stdout + result.stderr

# =====================================
# LLM QUERY FUNCTION
# =====================================
def query_llm(prompt_text):
    if LLM_PROVIDER == "openai":
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": OPENAI_MODEL, "messages": [{"role": "user", "content": prompt_text}]},
            timeout=120
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    elif LLM_PROVIDER == "anthropic":
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            json={"model": ANTHROPIC_MODEL, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt_text}]},
            timeout=120
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]

    elif LLM_PROVIDER == "gemini":
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            params={"key": GEMINI_API_KEY},
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt_text}]}]},
            timeout=120
        )
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]

    elif LLM_PROVIDER == "deepseek":
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt_text}]},
            timeout=120
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    elif LLM_PROVIDER == "huggingface":
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{HF_MODEL}",
            headers={"Authorization": f"Bearer {HF_API_KEY}", "Content-Type": "application/json"},
            json={"inputs": prompt_text, "parameters": {"max_new_tokens": 1024, "return_full_text": False}},
            timeout=1200
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data[0].get("generated_text", "")
        return data.get("generated_text", str(data))

    elif LLM_PROVIDER == "ollama":
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt_text, "stream": False},
            timeout=300
        )
        response.raise_for_status()
        return response.json()["response"]

    else:
        raise ValueError("Invalid LLM_PROVIDER")

# =====================================
# EXTRACT RTL MODULES
# =====================================
def extract_modules(text):
    text = re.sub(r"```[a-zA-Z]*", "", text)
    text = re.sub(r"```", "", text)
    matches = re.findall(r"(module\s[\s\S]*?endmodule)", text)
    if not matches:
        return None
    return "\n\n".join(m.strip() for m in matches)

# =====================================
# EXTRACT TOP MODULE FROM GENERATED RTL
# =====================================
def extract_top_module(text):
    modules = re.findall(r"module\s+(\w+)", text)
    if not modules:
        return None

    instantiations = re.findall(r"\b(\w+)\s+\w+\s*\(", text)
    keywords = {"if", "for", "while", "case", "assign", "always", "module", "wire", "reg", "logic"}
    instantiations = [m for m in instantiations if m not in keywords]
    top_candidates = [m for m in modules if m not in instantiations]

    if len(top_candidates) == 1:
        return top_candidates[0]
    if len(top_candidates) > 1:
        return top_candidates[-1]
    return modules[-1]

# =====================================
# P-STAGE: PORT SIGNATURE CHECK
# =====================================
def port_signature_check(text, top_module, rtl_file):
    issues = []

    header = re.search(rf"module\s+{top_module}\s*(#\s*\(.*?\))?\s*\((.*?)\)\s*;", text, re.S)
    if not header:
        return ["malformed module header"]

    ports_block = header.group(2)
    ports = []

    decls = re.findall(r'(input|output|inout)\s+(?:wire|reg|logic)?\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*;', text)
    for direction, port_name in decls:
        ports.append((direction, None, port_name))

    if re.search(r"\b(input|output|inout)\b", ports_block):
        lines = ports_block.split(",")
        for line in lines:
            line = line.strip()
            direction_match = re.search(r"(input|output|inout)", line)
            if not direction_match:
                continue
            direction = direction_match.group(1)
            width_match = re.search(r"(\[[^\]]+\])", line)
            width = width_match.group(1) if width_match else None
            names = re.findall(r"\b([a-zA-Z_]\w*)\b", line)
            for keyword in ["input", "output", "inout", "wire", "reg", "logic"]:
                if keyword in names:
                    names.remove(keyword)
            for name in names:
                if not any(p[2] == name for p in ports):
                    ports.append((direction, width, name))

    if not ports:
        port_names = re.findall(r"\b([a-zA-Z_]\w*)\b", ports_block)
        keywords = {"input", "output", "inout", "wire", "reg", "logic", "module"}
        for name in port_names:
            if name not in keywords and not any(p[2] == name for p in ports):
                ports.append((None, None, name))

    if not ports:
        issues.append("no valid port declarations found")
        return issues

    names = [p[2] for p in ports]
    if len(names) != len(set(names)):
        issues.append("duplicate port names detected")

    for _, width, name in ports:
        if width and not re.match(r"\[\s*\d+\s*:\s*\d+\s*\]", width):
            issues.append(f"invalid width for port {name}")

    rc, log = run_cmd(["yosys", "-p", f"read_verilog {rtl_file}; hierarchy -check -top {top_module}"])
    open(f"{RESULT_DIR}/P_yosys.log", "w").write(log)

    if rc != 0 or "ERROR" in log.upper():
        issues.append("yosys hierarchy check failed")

    return issues

# =====================================
# M-STAGE: MODULE QUALITY CHECK
# =====================================
def module_check(text):
    issues = []

    if re.search(r"\b(TODO|FIXME|TBD|XXX)\b", text, re.IGNORECASE):
        issues.append("placeholder found")

    if "case" in text and "default" not in text:
        issues.append("missing default case")

    if re.search(r"always\s*@\([^)]*\)\s*begin\s*end", text):
        issues.append("empty always block")

    module_count = len(re.findall(r'^\s*module\s+\w+', text, re.MULTILINE))
    endmodule_count = len(re.findall(r'^\s*endmodule', text, re.MULTILINE))

    if module_count != endmodule_count:
        issues.append("truncated module")

    if "assign" not in text and "always" not in text:
        issues.append("no logic found")

    return issues

# =====================================
# GET REFERENCE FILES
# =====================================
def get_reference_files():
    """Returns list of reference files (handles both single file and directory)"""
    reference_files = []
    
    if os.path.exists(REFERENCE_PATH) and os.path.isdir(REFERENCE_PATH):
        reference_files = [os.path.join(REFERENCE_PATH, f) for f in sorted(os.listdir(REFERENCE_PATH)) 
                          if f.endswith('.v')]
        if reference_files:
            print(f"[i] Found reference directory with {len(reference_files)} file(s):")
            for f in reference_files:
                print(f"    - {os.path.basename(f)}")
    
    elif os.path.exists(f"{REFERENCE_PATH}.v"):
        reference_files = [f"{REFERENCE_PATH}.v"]
        print(f"[i] Found single reference file: {REFERENCE_PATH}.v")
    
    elif os.path.exists(REFERENCE_PATH):
        reference_files = [REFERENCE_PATH]
        print(f"[i] Found reference file: {REFERENCE_PATH}")
    
    return reference_files

# =====================================
# LOAD PROMPT + QUERY LLM
# =====================================
if not os.path.exists(PROMPT_FILE):
    print(f"[!] Prompt file not found: {PROMPT_FILE}")
    sys.exit(0)

prompt = open(PROMPT_FILE).read()

print(f"[i] Querying LLM via provider: {LLM_PROVIDER}")
raw = query_llm(prompt)
open(RAW_FILE, "w").write(raw)

rtl = extract_modules(raw)

if not rtl:
    print("[!] No RTL found in LLM response")
    sys.exit(0)

open(RTL_FILE, "w").write(rtl)

# =====================================
# DETECT TOP MODULE FROM GENERATED RTL
# =====================================
generated_top_module = extract_top_module(rtl)

if not generated_top_module:
    print("[!] Could not detect top module from generated RTL")
    sys.exit(0)

print(f"[i] Detected generated top module: {generated_top_module}")

# =====================================
# DETERMINE REFERENCE TOP MODULE NAME
# =====================================
if REFERENCE_TOP_NAME:
    ref_top_module = REFERENCE_TOP_NAME
    print(f"[i] Using specified reference top module: {ref_top_module}")
else:
    ref_top_module = generated_top_module
    print(f"[i] Using same top module name for reference: {ref_top_module}")

# =====================================
# RESULT TRACKING
# =====================================
res = {
    "design":   DESIGN,
    "provider": LLM_PROVIDER,
    "P": "FAIL",
    "C": "FAIL",
    "M": "PASS",
    "E": "FAIL",
    "F": "FAIL",
    "S": "FAIL",
    "time": 0
}

# =====================================
# P-STAGE: PORT SIGNATURE CHECK
# =====================================
issues = port_signature_check(rtl, generated_top_module, RTL_FILE)

if issues:
    print("[!] P-stage FAILED")
    print(f"Issues: {issues}")
    res["P"] = "FAIL"
    print(json.dumps(res))
    sys.exit(0)

res["P"] = "PASS"
print("[i] P-stage PASSED")

# =====================================
# C-STAGE: IVERILOG SYNTAX CHECK
# =====================================
rc, _ = run_cmd(["iverilog", "-tnull", RTL_FILE])
if rc != 0:
    print("[!] C-stage FAILED")
    res["C"] = "FAIL"
    print(json.dumps(res))
    sys.exit(0)

res["C"] = "PASS"
print("[i] C-stage PASSED")

# =====================================
# M-STAGE: MODULE QUALITY CHECK
# =====================================
issues = module_check(rtl)
res["M"] = "PASS" if not issues else "FAIL"
if res["M"] == "PASS":
    print("[i] M-stage PASSED")
else:
    print(f"[!] M-stage FAILED - Issues: {issues}")

# =====================================
# E-STAGE: YOSYS ELABORATION
# =====================================
rc, _ = run_cmd(["yosys", "-p", f"read_verilog {RTL_FILE}; hierarchy -check -top {generated_top_module}"])

if rc != 0:
    print("[!] E-stage FAILED")
    res["E"] = "FAIL"
    print(json.dumps(res))
    sys.exit(0)

res["E"] = "PASS"
print("[i] E-stage PASSED")

# =====================================
# F-STAGE: FORMAL EQUIVALENCE CHECK
# =====================================
reference_files = get_reference_files()

if reference_files:
    print(f"[i] Running formal equivalence check...")
    print(f"    Generated top module: {generated_top_module}")
    print(f"    Reference top module: {ref_top_module}")
    
    # Build Yosys script
    yosys_script = "# Read all reference files\n"
    for ref_file in reference_files:
        yosys_script += f"read_verilog {ref_file}\n"
    
    yosys_script += f"""
# Read generated RTL
read_verilog {RTL_FILE}

# Prepare for equivalence check
prep -top {generated_top_module}

# Create equivalence check between generated and reference
# Generated: {generated_top_module}
# Reference: {ref_top_module}
equiv_make -flatten {generated_top_module} {ref_top_module}
equiv_simple

# Check equivalence
equiv_status -assert

# If we reach here, designs are equivalent
puts "Designs are equivalent"
"""
    
    equiv_script_file = f"{RESULT_DIR}/equiv_check.ys"
    with open(equiv_script_file, "w") as f:
        f.write(yosys_script)
    
    rc, log = run_cmd(["yosys", "-s", equiv_script_file])
    open(f"{RESULT_DIR}/F_yosys.log", "w").write(log)
    
    if rc == 0:
        res["F"] = "PASS"
        print(f"[i] F-stage: PASSED - Designs are equivalent")
    else:
        res["F"] = "FAIL"
        print(f"[i] F-stage: FAILED")
        
        if "Equivalence failed" in log:
            print("   Designs are NOT functionally equivalent")
        elif "ERROR" in log:
            print("   Yosys encountered an error during equivalence check")
        elif "Can't find module" in log:
            print(f"   Yosys cannot find module '{ref_top_module}' in reference files")
else:
    print("[i] F-stage skipped: no reference file(s) found")
    res["F"] = "SKIPPED"

# =====================================
# S-STAGE: REMOTE SYNTHESIS (GENUS)
# =====================================
print("\n[i] Running S-stage (Remote Synthesis)...")

rc, log = run_cmd([
    "sshpass", "-p", SSH_PASS,
    "ssh", "-o", "StrictHostKeyChecking=no",
    f"{REMOTE_USER}@{REMOTE_HOST}",
    f"mkdir -p {REMOTE_DIR}"
])

if rc != 0:
    print("[!] S-stage FAILED - Could not create remote directory")
    print(f"   Error: {log}")
    open(f"{RESULT_DIR}/S.log", "w").write(log)
    res["time"] = round(time.time() - start_time, 3)
    print(json.dumps(res))
    sys.exit(0)

print(f"   Created directory: {REMOTE_DIR}")

rc, log = run_cmd([
    "sshpass", "-p", SSH_PASS,
    "scp", "-o", "StrictHostKeyChecking=no",
    RTL_FILE,
    f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_DIR}/design.v"
])

if rc != 0:
    print("[!] S-stage FAILED - Could not copy RTL file")
    print(f"   Error: {log}")
    open(f"{RESULT_DIR}/S.log", "w").write(log)
    res["time"] = round(time.time() - start_time, 3)
    print(json.dumps(res))
    sys.exit(0)

print(f"   Copied RTL file: {RTL_FILE}")

genus_script = f"""
set_db use_scan_seqs_for_non_dft false
set_db init_lib_search_path /home/cadence/install/FOUNDRY/digital/90nm/dig/lib/
set_db init_hdl_search_path {REMOTE_DIR}

read_libs slow.lib
read_hdl ./design.v
elaborate {generated_top_module}

set_db syn_generic_effort medium
set_db syn_map_effort medium
set_db syn_opt_effort medium

syn_generic
syn_map
syn_opt

redirect timing.rpt {{ report_timing }}
redirect area.rpt   {{ report_area }}
redirect power.rpt  {{ report_power }}

exit
"""

with open("temp.tcl", "w") as f:
    f.write(genus_script)

if os.path.exists("temp.tcl"):
    print("   Created temp.tcl")
else:
    print("[!] Failed to create temp.tcl")
    sys.exit(0)

rc, log = run_cmd([
    "sshpass", "-p", SSH_PASS,
    "scp", "-o", "StrictHostKeyChecking=no",
    "temp.tcl",
    f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_DIR}/genus.tcl"
])

if os.path.exists("temp.tcl"):
    os.remove("temp.tcl")

if rc != 0:
    print("[!] S-stage FAILED - Could not copy TCL script")
    print(f"   Error: {log}")
    open(f"{RESULT_DIR}/S.log", "w").write(log)
    res["time"] = round(time.time() - start_time, 3)
    print(json.dumps(res))
    sys.exit(0)

print("   Copied TCL script to remote server")

print(f"   Running Genus on {REMOTE_HOST}:{REMOTE_DIR}")

rc, log = run_cmd([
    "sshpass", "-p", SSH_PASS,
    "ssh", "-o", "StrictHostKeyChecking=no",
    f"{REMOTE_USER}@{REMOTE_HOST}",
    f"csh -c 'cd {REMOTE_DIR}; genus -batch -files genus.tcl'"
])

if rc != 0:
    print("   Trying alternative Genus invocation...")
    rc, log = run_cmd([
        "sshpass", "-p", SSH_PASS,
        "ssh", "-o", "StrictHostKeyChecking=no",
        f"{REMOTE_USER}@{REMOTE_HOST}",
        f"cd {REMOTE_DIR} && genus -batch -files genus.tcl"
    ])

open(f"{RESULT_DIR}/S.log", "w").write(log)

if rc != 0:
    print(f"   Genus returned error code: {rc}")
    print(f"   Check {RESULT_DIR}/S.log for details")

reports = ["timing.rpt", "area.rpt", "power.rpt"]
all_reports_copied = True

for rpt in reports:
    rc2, log2 = run_cmd([
        "sshpass", "-p", SSH_PASS,
        "scp", "-o", "StrictHostKeyChecking=no",
        f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_DIR}/{rpt}",
        f"{RESULT_DIR}/{rpt}"
    ])
    if rc2 != 0:
        all_reports_copied = False
        print(f"   Warning: Could not copy {rpt}")
    else:
        print(f"   Copied {rpt}")

if rc == 0 and all_reports_copied and "Error" not in log and "fail" not in log.lower():
    res["S"] = "PASS"
    print("[i] S-stage PASSED")
else:
    res["S"] = "FAIL"
    print("[!] S-stage FAILED")
    if rc != 0:
        print(f"   Genus returned error code: {rc}")
    if not all_reports_copied:
        print("   Some report files were not copied back")
    if "Error" in log:
        print("   Genus reported errors in log")
    if "fail" in log.lower():
        print("   Genus reported failures in log")

# =====================================
# FINAL RESULT
# =====================================
res["time"] = round(time.time() - start_time, 3)

print("\n===== FINAL RESULT =====")
print("__JSON_START__")
print(json.dumps(res))
print("__JSON_END__")
