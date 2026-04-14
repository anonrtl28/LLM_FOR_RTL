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
DESIGN = "half_adder" # change design name here

# =====================================
# LLM PROVIDER CONFIGURATION
# =====================================
# Supported providers:
#   "openai"      - OpenAI API
#   "anthropic"   - Claude (Anthropic)
#   "gemini"      - Google Gemini
#   "deepseek"    - DeepSeek API
#   "huggingface" - HuggingFace Inference API

LLM_PROVIDER = "openai"

# --- OpenAI ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
OPENAI_MODEL   = "gpt-4o" #change model here if needed

# --- Claude ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_API_KEY")
ANTHROPIC_MODEL   = "claude-3-5-sonnet-20241022" # change model here if needed

# --- Gemini ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
GEMINI_MODEL   = "gemini-1.5-pro" # change model if needed

# --- DeepSeek ---
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_API_KEY")
DEEPSEEK_MODEL   = "deepseek-coder" #Change model if needed

# --- HuggingFace ---
HF_API_KEY = os.environ.get("HF_API_KEY", "YOUR_HF_API_TOKEN")
HF_MODEL   = "shailja/fine-tuned-codegen-16B-Verilog" #change the model here

# =====================================
# FILE PATHS
# =====================================
PROMPT_FILE    = f"prompts/{DESIGN}.txt"
RTL_FILE       = f"rtl/{DESIGN}.v"
RAW_FILE       = f"rtl/raw_output.txt"
REFERENCE_FILE = f"reference/{DESIGN}.v"
RESULT_DIR     = f"results/{DESIGN}"

# =====================================
# SSH CONFIG
# =====================================
REMOTE_USER = "YOUR_USERNAME"
REMOTE_HOST = "YOUR_HOST"
REMOTE_DIR  = "/path/to/synthesis"
SSH_PASS    = os.environ.get("SSH_PASS", "")

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
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt_text}]
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    elif LLM_PROVIDER == "anthropic":
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt_text}]
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]

    elif LLM_PROVIDER == "gemini":
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            params={"key": GEMINI_API_KEY},
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": prompt_text}]
                }]
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]

    elif LLM_PROVIDER == "deepseek":
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt_text}]
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    elif LLM_PROVIDER == "huggingface":
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{HF_MODEL}",
            headers={
                "Authorization": f"Bearer {HF_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "inputs": prompt_text,
                "parameters": {
                    "max_new_tokens": 1024,
                    "return_full_text": False
                }
            },
            timeout=1200
        )
        response.raise_for_status()

        data = response.json()
        if isinstance(data, list):
            return data[0].get("generated_text", "")
        return data.get("generated_text", str(data))

    else:
        raise ValueError("Invalid LLM_PROVIDER")


# =====================================
# SSH HELPERS
# =====================================
def run_remote(cmd):
    return run_cmd([
        "sshpass", "-p", SSH_PASS,
        "ssh", "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=30",
        "-t",
        f"{REMOTE_USER}@{REMOTE_HOST}",
        cmd
    ])

def scp_to(local, remote):
    return run_cmd([
        "sshpass", "-p", SSH_PASS,
        "scp", "-o", "StrictHostKeyChecking=no",
        local,
        f"{REMOTE_USER}@{REMOTE_HOST}:{remote}"
    ])

def scp_from(remote, local):
    return run_cmd([
        "sshpass", "-p", SSH_PASS,
        "scp", "-o", "StrictHostKeyChecking=no",
        f"{REMOTE_USER}@{REMOTE_HOST}:{remote}",
        local
    ])

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
# EXTRACT TOP MODULE
# =====================================
def extract_top_module(text):
    modules = re.findall(r"module\s+(\w+)", text)

    if not modules:
        return None

    instantiations = re.findall(r"\b(\w+)\s+\w+\s*\(", text)

    keywords = {
        "if", "for", "while", "case", "assign",
        "always", "module", "wire", "reg", "logic"
    }

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

    header = re.search(
        rf"module\s+{top_module}\s*(#\s*\(.*?\))?\s*\((.*?)\)\s*;",
        text,
        re.S
    )

    if not header:
        return ["malformed module header"]

    ports_block = header.group(2)
    ports = []

    # ANSI-style port declarations
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
                ports.append((direction, width, name))

    # Non-ANSI (old-style) port declarations
    else:
        port_names = re.findall(r"\b([a-zA-Z_]\w*)\b", ports_block)
        decls = re.findall(r"(input|output|inout)[^;]+;", text)

        for decl in decls:
            direction = re.search(r"(input|output|inout)", decl).group(1)

            width_match = re.search(r"(\[[^\]]+\])", decl)
            width = width_match.group(1) if width_match else None

            names = re.findall(r"\b([a-zA-Z_]\w*)\b", decl)

            for keyword in ["input", "output", "inout", "wire", "reg", "logic"]:
                if keyword in names:
                    names.remove(keyword)

            for name in names:
                if name in port_names:
                    ports.append((direction, width, name))

    if not ports:
        issues.append("no valid port declarations found")

    names = [p[2] for p in ports]
    if len(names) != len(set(names)):
        issues.append("duplicate port names detected")

    for _, width, name in ports:
        if width and not re.match(r"\[\s*\d+\s*:\s*\d+\s*\]", width):
            issues.append(f"invalid width for port {name}")

    # Yosys hierarchy check
    rc, log = run_cmd([
        "yosys", "-p",
        f"read_verilog {rtl_file}; hierarchy -check -top {top_module}"
    ])

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

    if text.count("module") != text.count("endmodule"):
        issues.append("truncated module")

    if "assign" not in text and "always" not in text:
        issues.append("no logic")

    return issues

# =====================================
# LOAD PROMPT + QUERY LLM
# =====================================
if not os.path.exists(PROMPT_FILE):
    print(f"[!] Prompt file not found: {PROMPT_FILE}")
    print(json.dumps(res))
    sys.exit(0)


prompt = open(PROMPT_FILE).read()

print(f"[i] Querying LLM via provider: {LLM_PROVIDER}")
raw = query_llm(prompt)
open(RAW_FILE, "w").write(raw)

rtl = extract_modules(raw)

if not rtl:
    print("[!] No RTL found in LLM response")
    print(json.dumps(res))
    sys.exit(0)

open(RTL_FILE, "w").write(rtl)

# =====================================
# DETECT TOP MODULE
# =====================================
top_module = extract_top_module(rtl)

print("[!] Could not detect top module")
    print(json.dumps(res))
    sys.exit(0)

print(f"[i] Detected top module: {top_module}")

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
issues = port_signature_check(rtl, top_module, RTL_FILE)

if rc != 0:
    print("[!] P-stage FAILED")
    res["P"] = "FAIL"
    print(json.dumps(res))
    sys.exit(0)

res["P"] = "PASS"

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

# =====================================
# M-STAGE: MODULE QUALITY CHECK
# =====================================
issues = module_check(rtl)
res["M"] = "PASS" if not issues else "FAIL"

# =====================================
# E-STAGE: YOSYS ELABORATION
# =====================================
rc, _ = run_cmd([
    "yosys", "-p",
    f"read_verilog {RTL_FILE}; hierarchy -check -top {top_module}"
])

if rc != 0:
    print("[!] E-stage FAILED")
    res["E"] = "FAIL"
    print(json.dumps(res))
    sys.exit(0)

res["E"] = "PASS"

# =====================================
# F-STAGE: FORMAL EQUIVALENCE CHECK
# Compares generated RTL against a
# reference implementation using Yosys.
# Requires a file at: reference/<design>.v
# =====================================
if os.path.exists(REFERENCE_FILE):
    rc, _ = run_cmd(["yosys", "-p", "equiv_simple"])
    res["F"] = "PASS" if rc == 0 else "FAIL"
else:
    print("[i] F-stage skipped: no reference file found")

# =====================================
# S-STAGE: REMOTE SYNTHESIS
# Runs logic synthesis on a remote server
# using Cadence Genus (or adapt the TCL
# script below for your own tool, e.g.
# Synopsys Design Compiler, Yosys+ABC).
#
# Requirements on remote machine:
#   - Genus (or compatible synthesis tool)
#   - sshpass installed locally
# =====================================
run_remote(f"mkdir -p {REMOTE_DIR}")
scp_to(RTL_FILE, f"{REMOTE_DIR}/design.v")

# Adapt this TCL script for your synthesis tool
open("temp.tcl", "w").write(f"""
read_hdl design.v
elaborate {top_module}
syn_generic
syn_map
syn_opt
report_area > area.rpt
report_timing > timing.rpt
exit
""")

scp_to("temp.tcl", f"{REMOTE_DIR}/genus.tcl")
os.remove("temp.tcl")

# Change 'genus -batch -files' to match your tool's invocation
rc, _ = run_remote(f"cd {REMOTE_DIR} && genus -batch -files genus.tcl")

scp_from(f"{REMOTE_DIR}/area.rpt",   f"{RESULT_DIR}/area.rpt")
scp_from(f"{REMOTE_DIR}/timing.rpt", f"{RESULT_DIR}/timing.rpt")

res["S"] = "PASS" if rc == 0 else "FAIL"

# =====================================
# FINAL RESULT
# =====================================
res["time"] = round(time.time() - start_time, 3)

print("\n===== FINAL RESULT =====")
print(json.dumps(res))
