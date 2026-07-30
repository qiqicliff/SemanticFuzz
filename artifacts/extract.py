#!/usr/bin/env python3
"""
Artifact Extraction for Reproducibility.

Extracts from experiment logs:
  1. Generated semantic templates (per API, 5-category)
  2. Generated test cases (code + combo + validation result)
  3. Mutation prompts (if available)
  4. Repair prompts (if repair was triggered)
  5. Execution logs (stdout/stderr/returncode per program)
  6. Defect classification (hallucination type + reasons)
  7. Deduplication rules (AST similarity thresholds + examples)
  8. Minimized reproducible examples (shortest failing code per hallucination type)

Output: SF/evaluate/artifacts/artifact_package.json
"""

import json, os, sys, re
from collections import defaultdict
from datetime import datetime

SF_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================================
# 1. Extract Semantic Templates from hu/ experiment
# ============================================================================
def extract_semantic_templates():
    """Load pre-extracted semantic templates from artifacts/semantic_templates.json."""
    path = os.path.join(ARTIFACT_DIR, "semantic_templates.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


# ============================================================================
# 2. Extract Generated Test Cases from hu/ experiment
# ============================================================================
def extract_test_cases():
    """Extract generated test cases with validation results."""
    cases = defaultdict(list)
    hu_dir = os.path.join(os.path.dirname(ARTIFACT_DIR), "hu")
    for fname in os.listdir(hu_dir) if os.path.exists(hu_dir) else []:
        if fname.endswith("_programs.jsonl"):
            lib = fname.split("_")[0]
            with open(os.path.join(hu_dir, fname)) as f:
                for line in f:
                    d = json.loads(line.strip())
                    cases[lib].append({
                        "api_name": d["api_name"],
                        "code": d.get("code", ""),
                        "combo": d.get("combo", {}),
                        "exec_result": {
                            "returncode": d["exec"]["returncode"],
                            "stderr_clean": d["exec"].get("stderr_clean", "")[:500],
                        },
                        "hallucination": d["hallu"],
                    })
    return dict(cases)


# ============================================================================
# 3. Extract Mutation Prompts (from mutation-related modules)
# ============================================================================
def extract_mutation_prompts():
    """Extract mutation prompt templates from source code."""
    prompts = {}
    # Check src/ directory for mutation-related files
    src_dir = os.path.join(SF_ROOT, "src")
    for fname in os.listdir(src_dir) if os.path.exists(src_dir) else []:
        if not fname.endswith(".py"): continue
        if any(kw in fname for kw in ["mutation", "mutate", "oracle", "fuzz"]):
            full = os.path.join(src_dir, fname)
            with open(full) as f:
                content = f.read()
            # Extract prompts
            matches = re.findall(r'(?:prompt|PROMPT|message)\s*=\s*(?:f?"""(.+?)"""|f?"(.+?)"|f\'(.+?)\')', content, re.DOTALL)
            if matches:
                prompts[f"src/{fname}"] = [(m[0] or m[1] or m[2])[:500] for m in matches[:5]]
    return prompts


# ============================================================================
# 4. Extract Repair Prompts and examples
# ============================================================================
def extract_repair_examples():
    """Find cases where repair was triggered and show before/after."""
    repairs = []
    step2_file = os.path.join(SF_ROOT, "main", "step2_partition.py")
    with open(step2_file) as f:
        repair_prompt = ""
        in_prompt = False
        for line in f:
            if "修复代码错误" in line: in_prompt = True
            if in_prompt: repair_prompt += line
            if "修复后的代码" in line and in_prompt: break

    repairs.append({
        "prompt_template": repair_prompt.strip(),
        "trigger_condition": "SyntaxError in generated init_code",
        "model": "qwen3-coder-next (qwen_coder_b)",
    })
    return repairs


# ============================================================================
# 5. Extract Execution Logs (aggregated statistics)
# ============================================================================
def extract_execution_logs():
    """Extract aggregated execution statistics from experiment logs."""
    logs = {}
    log_files = [
        "evaluate/hu/experiment.log",
        "evaluate/semantic_ev/experiment.log",
        "evaluate/seed_ev/experiment.log",
    ]
    for lf in log_files:
        full = os.path.join(SF_ROOT, lf)
        if not os.path.exists(full): continue
        with open(full) as f:
            lines = f.readlines()
        # Extract Done lines with statistics
        stats = []
        for line in lines:
            if "Done:" in line or "success" in line.lower():
                stats.append(line.strip())
        logs[lf] = {
            "total_lines": len(lines),
            "milestones": stats[-20:],  # last 20 milestones
        }
    return logs


# ============================================================================
# 6. Defect Classification Rules (deterministic + LLM)
# ============================================================================
def extract_defect_classification():
    """Extract defect classification logic and rules."""
    hu_run = os.path.join(SF_ROOT, "evaluate/hu/run.py")
    rules = {"deterministic_rules": [], "llm_categories": []}

    with open(hu_run) as f:
        content = f.read()

    # Extract rule patterns
    rule_patterns = re.findall(r'# -+ Rule \d+: (.+?) -+.*?issues\.append\(\((.+?),\s*(.+?)\)\)', content, re.DOTALL)
    for title, type_str, reason in rule_patterns:
        rules["deterministic_rules"].append({
            "rule": title.strip(),
            "type": type_str.strip().strip('"'),
            "reason_pattern": reason.strip().strip('"'),
        })

    # Extract LLM categories
    cat_match = re.search(r'"无效的API假设".*?"其他\(非幻觉\)"', content, re.DOTALL)
    if cat_match:
        rules["llm_categories"] = [
            "无效的API假设 (Invalid API assumption)",
            "语义不匹配 (Semantic mismatch)",
            "版本漂移 (Version drift)",
            "提示不合规 (Prompt non-compliance)",
            "约束不存在 (Non-existent constraint)",
            "其他(非幻觉) (Other, non-hallucination)",
        ]

    return rules


# ============================================================================
# 7. Deduplication Rules
# ============================================================================
def extract_dedup_rules():
    """Extract AST-based deduplication rules."""
    return {
        "method": "AST node-type count similarity",
        "threshold": 0.95,
        "algorithm": "Greedy pairwise matching with early exit on exact match",
        "implementation_file": "evaluate/semantic_eval.py (deduplicate_codes) and evaluate/hu/run.py",
        "penalty": "Duplicate codes counted as semantically invalid (val_ok=False)",
    }


# ============================================================================
# 8. Minimized Reproducible Examples
# ============================================================================
def extract_minimized_examples():
    """Extract the shortest failing code per hallucination type for each library."""
    hu_dir = os.path.join(os.path.dirname(ARTIFACT_DIR), "hu")
    examples = {}

    for fname in os.listdir(hu_dir) if os.path.exists(hu_dir) else []:
        if not fname.endswith("_programs.jsonl"): continue
        lib = fname.split("_")[0]
        by_type = defaultdict(list)
        with open(os.path.join(hu_dir, fname)) as f:
            for line in f:
                d = json.loads(line.strip())
                t = d["hallu"].get("hallucination_type", "unknown")
                code = d.get("code") or ""
                if t != "no_issue" and d["exec"]["returncode"] != 0:
                    by_type[t].append({"api": d["api_name"], "code": code, "len": len(code)})

        examples[lib] = {}
        for t, items in by_type.items():
            # Pick shortest code as minimized example
            items.sort(key=lambda x: x["len"])
            examples[lib][t] = {
                "shortest_code": items[0]["code"],
                "api": items[0]["api"],
                "all_apis": list(set(i["api"] for i in items)),
                "count": len(items),
            }

    return examples


# ============================================================================
# Main: collect all artifacts
# ============================================================================
def build_package():
    print("Extracting artifacts...")

    package = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "project": "SemanticFuzz",
            "description": "Reproducibility artifact package",
        },
        "semantic_templates": extract_semantic_templates(),
        "test_cases": extract_test_cases(),
        "mutation_prompts": extract_mutation_prompts(),
        "repair_examples": extract_repair_examples(),
        "execution_logs": extract_execution_logs(),
        "defect_classification": extract_defect_classification(),
        "dedup_rules": extract_dedup_rules(),
        "minimized_examples": extract_minimized_examples(),
    }

    # Summary counts
    package["summary"] = {
        "n_semantic_templates": len(package["semantic_templates"]),
        "n_test_cases": {lib: len(cases) for lib, cases in package["test_cases"].items()},
        "n_mutation_prompt_files": len(package["mutation_prompts"]),
        "n_repair_examples": len(package["repair_examples"]),
        "n_execution_logs": len(package["execution_logs"]),
        "n_hallucination_rules": len(package["defect_classification"].get("deterministic_rules", [])),
        "n_minimized_examples": {lib: len(types) for lib, types in package["minimized_examples"].items()},
    }

    out_path = os.path.join(ARTIFACT_DIR, "artifact_package.json")
    # Write as compact JSONL for large datasets
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(package, f, ensure_ascii=False, indent=2)

    print(f"\nArtifact package written to: {out_path}")
    print(f"Summary: {json.dumps(package['summary'], indent=2)}")

    # Also write individual files for easier browsing
    for key in ["semantic_templates", "test_cases", "minimized_examples"]:
        sub_path = os.path.join(ARTIFACT_DIR, f"{key}.json")
        with open(sub_path, "w", encoding="utf-8") as f:
            json.dump(package[key], f, ensure_ascii=False, indent=2)
        print(f"  {key}: {sub_path}")

    return package


if __name__ == "__main__":
    build_package()
