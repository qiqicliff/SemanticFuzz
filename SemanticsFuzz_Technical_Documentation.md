# SemanticsFuzz: A Semantic-Driven Deep Learning Fuzzing Framework

> **Technical Documentation v1.0**  
> Target: PyTorch & TensorFlow Deep Learning Libraries  
> Core Paradigm: Semantic-Aware Fuzzing

---

## 1. Introduction

### 1.1 Overview

**SemanticsFuzz** is a state-of-the-art fuzzing framework specifically engineered for deep learning (DL) libraries, with primary focus on **PyTorch** and **TensorFlow**. Unlike conventional fuzzers that rely solely on random input generation, SemanticsFuzz employs a **semantic-driven mutation strategy** that preserves the structural and logical integrity of computational graphs while exploring edge cases and vulnerability-triggering patterns.

### 1.2 Core Architecture

The framework operates through a three-stage pipeline:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Extractor &    │ ──▶ │    Recomposer   │ ──▶ │   Fuzzing Loop  │
│  Decomposer     │     │   (Mutation)    │     │   (Execution)   │
│  (partition.py) │     │(partition_mutation│    │   (main.py)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
       │                       │                       │
       ▼                       ▼                       ▼
  Model Partitioning      Semantic Mutation        Crash Detection
  & Graph Analysis       & Structure Preservation   & Coverage Guided
```

#### 1.2.1 Key Components

| Component                | Module                  | Functionality                                                                                                |
| ------------------------ | ----------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Extractor_Decomposer** | `partition.py`          | Decomposes DL models into semantic units, extracts computational subgraphs, and performs dependency analysis |
| **Recomposer**           | `partition_mutation.py` | Applies semantic-preserving mutations, recombines subgraphs with controlled perturbations                    |
| **Fuzzing Engine**       | `main.py`               | Orchestrates the fuzzing loop, manages state transitions, and handles crash triage                           |

### 1.3 Semantic-Driven Approach

Traditional fuzzers for DL libraries treat APIs as black-box functions. SemanticsFuzz introduces **semantic awareness** through:

- **Type-Conserving Mutations**: Ensures tensor dimensions and data types remain valid post-mutation
- **Graph Structural Integrity**: Maintains DAG (Directed Acyclic Graph) properties during subgraph manipulation
- **Gradient Flow Preservation**: For trainable operations, ensures backward compatibility
- **Device Placement Awareness**: Respects CPU/GPU/TPU placement constraints

---

## 2. Environment Setup

### 2.1 Prerequisites

- **Python**: 3.9+ (3.10 recommended for TensorFlow compatibility)
- **CUDA**: 12.x or 13.x (for GPU acceleration)
- **Package Manager**: `uv` (ultra-fast Python package manager)

### 2.2 UV Installation

```bash
# Install uv package manager (if not already installed)
pip install uv

# Verify installation
uv --version
```

### 2.3 PyTorch Environment Configuration

Create an isolated virtual environment for PyTorch testing:

```bash
# Navigate to project root
cd /path/to/SemanticsFuzz

# Create virtual environment
uv venv .venv_pt --python 3.10

# Activate environment
source .venv_pt/bin/activate  # Linux/Mac
# OR
.venv_pt\Scripts\activate    # Windows

# Install PyTorch with CUDA 13.1 support
uv pip install torch torchvision torchaudio     --index-url https://download.pytorch.org/whl/cu131

# Verify GPU availability
python -c "
import torch
print(f'PyTorch Version: {torch.__version__}')
print(f'CUDA Available: {torch.cuda.is_available()}')
print(f'CUDA Version: {torch.version.cuda}')
print(f'GPU Count: {torch.cuda.device_count()}')
if torch.cuda.is_available():
    print(f'GPU Name: {torch.cuda.get_device_name(0)}')
"
```

### 2.4 TensorFlow Environment Configuration

Create a separate isolated environment for TensorFlow to avoid dependency conflicts:

```bash
# Create dedicated TensorFlow environment
uv venv .venv_tf --python 3.10

# Activate environment
source .venv_tf/bin/activate

# Install TensorFlow 2.17.0 with CUDA support
# Using Tsinghua mirror for accelerated download (China region)
uv pip install tensorflow[and-cuda]==2.17.0     -i https://pypi.tuna.tsinghua.edu.cn/simple

# Alternative: Official PyPI (for global users)
# uv pip install tensorflow[and-cuda]==2.17.0

# Verify GPU recognition
python -c "
import tensorflow as tf
print(f'TensorFlow Version: {tf.__version__}')
gpus = tf.config.list_physical_devices('GPU')
print(f'GPUs Detected: {len(gpus)}')
for gpu in gpus:
    print(f'  - {gpu}')
"
```

### 2.5 Environment Isolation Best Practices

```bash
# Project structure recommendation
SemanticsFuzz/
├── .venv_pt/          # PyTorch environment
├── .venv_tf/          # TensorFlow environment
├── Extractor_Decomposer/
├── Recomposer/
├── fuzz_loop/
└── shared_libs/       # Common utilities (symlinked or PYTHONPATH)

# Quick activation aliases (add to ~/.bashrc or ~/.zshrc)
alias activate_pt='source /path/to/SemanticsFuzz/.venv_pt/bin/activate'
alias activate_tf='source /path/to/SemanticsFuzz/.venv_tf/bin/activate'
```

### 2.6 Dependency Management

For reproducible environments, export lock files:

```bash
# PyTorch environment
source .venv_pt/bin/activate
uv pip freeze > requirements_pt.txt

# TensorFlow environment
source .venv_tf/bin/activate
uv pip freeze > requirements_tf.txt

# Synchronize on new machine
uv pip sync requirements_pt.txt  # or requirements_tf.txt
```

---

## 3. Execution Workflow

### 3.1 Stage 1: Model Extraction & Decomposition

**Script**: `Extractor_Decomposer/partition.py`

This module performs static and dynamic analysis of DL models to extract computational subgraphs.

```bash
# Activate appropriate environment
source .venv_pt/bin/activate  # For PyTorch models
# OR
source .venv_tf/bin/activate  # For TensorFlow models

# Run decomposition
cd Extractor_Decomposer
python partition.py     --model_path /path/to/model.pt     --output_dir ../artifacts/partitions/     --strategy semantic_graph     --max_depth 5
```

**Key Parameters**:

- `--strategy`: Partitioning algorithm (`semantic_graph`, `layer_wise`, `operation_wise`)
- `--max_depth`: Maximum recursion depth for subgraph extraction
- `--preserve_gradients`: Maintain gradient flow information (default: true)

### 3.2 Stage 2: Semantic Recomposition & Mutation

**Script**: `Recomposer/partition_mutation.py`

Applies semantic-aware mutations to partitioned subgraphs while preserving computational validity.

```bash
cd ../Recomposer

# Basic mutation execution
python partition_mutation.py     --input_dir ../artifacts/partitions/     --output_dir ../artifacts/mutations/     --mutation_policy semantic_aware     --mutation_rate 0.15     --max_mutations 1000

# Advanced: Target specific operation types
python partition_mutation.py     --input_dir ../artifacts/partitions/     --target_ops Conv2d,Linear,BatchNorm2d     --constraint_check strict
```

**Mutation Strategies**:

| Strategy         | Description                             | Use Case                  |
| ---------------- | --------------------------------------- | ------------------------- |
| `semantic_aware` | Preserves tensor shapes and dtypes      | General fuzzing           |
| `boundary_focus` | Targets numerical edge cases (NaN, Inf) | Stability testing         |
| `dtype_chaos`    | Systematic type casting mutations       | Type system robustness    |
| `device_shuffle` | Randomizes CPU/GPU placement            | Device management testing |

### 3.3 Stage 3: Fuzzing Loop Execution

**Script**: `fuzz_loop/main.py`

The main orchestration engine that executes mutated models, monitors for crashes, and manages coverage feedback.

```bash
cd ../fuzz_loop

# Standard fuzzing session
python main.py     --mutation_dir ../artifacts/mutations/     --backend pytorch     --timeout 3600     --coverage_guided     --crash_dir ../artifacts/crashes/

# TensorFlow backend with specific configuration
python main.py     --mutation_dir ../artifacts/mutations/     --backend tensorflow     --tf_gpu_memory_growth     --max_iterations 10000     --seed 42
```

**Execution Modes**:

```bash
# Continuous fuzzing with auto-resume
python main.py     --mutation_dir ../artifacts/mutations/     --backend pytorch     --resume_from ../artifacts/state.json     --daemon_mode

# Parallel fuzzing (multi-GPU setup)
python main.py     --mutation_dir ../artifacts/mutations/     --backend pytorch     --parallel_workers 4     --gpu_ids 0,1,2,3
```

---

## 4. Advanced Configuration

### 4.1 Semantic Constraint Definition

Define custom semantic rules in `config/semantic_rules.yaml`:

```yaml
# Example: PyTorch convolution constraints
constraints:
  torch.nn.Conv2d:
    input_shape:
      min_dims: 4
      max_dims: 4
      channel_alignment: 8 # CUDA optimization

    parameter_bounds:
      kernel_size: [1, 7]
      stride: [1, 4]
      padding: [0, 3]

    dtype_compatibility:
      valid_dtypes: [float32, float16, bfloat16]
      default: float32

  torch.matmul:
    shape_rules:
      - broadcast_compatible: true
      - matrix_multiply_compatible: true
    device_consistency: strict # All inputs on same device
```

### 4.2 Coverage-Guided Fuzzing Parameters

```python
# fuzz_loop/config.py excerpt
COVERAGE_CONFIG = {
    "edge_coverage": True,           # Branch coverage tracking
    "value_coverage": True,          # Interesting value discovery (NaN, 0, 1, etc.)
    "shape_coverage": True,          # Tensor shape diversity
    "dtype_coverage": True,          # Data type exploration
    "device_coverage": True,         # Cross-device execution paths
    "gradient_coverage": False,      # Backward pass coverage (computationally expensive)
}
```

---

## 5. Troubleshooting

### 5.1 Common Issues

**Issue**: `CUDA out of memory` during fuzzing

```bash
# Solution: Enable memory growth for TensorFlow
export TF_FORCE_GPU_ALLOW_GROWTH=true

# Or for PyTorch, configure in main.py:
# torch.cuda.empty_cache() between iterations
```

**Issue**: `ModuleNotFoundError` for shared libraries

```bash
# Ensure PYTHONPATH includes shared components
export PYTHONPATH=/path/to/SemanticsFuzz:$PYTHONPATH
```

**Issue**: UV environment conflicts

```bash
# Clean reinstall
rm -rf .venv_pt .venv_tf
uv cache clean
# Recreate environments as per Section 2
```

### 5.2 Debug Mode

Enable verbose logging across all stages:

```bash
export SEMANTICSFUZZ_DEBUG=1
export SEMANTICSFUZZ_LOG_LEVEL=DEBUG
python main.py --verbose
```

---

## 6. Citation

If you use SemanticsFuzz in your research, please cite:

```bibtex
@software{semanticsfuzz2024,
  title={SemanticsFuzz: Semantic-Driven Fuzzing for Deep Learning Libraries},
  author={[Authors]},
  year={2024},
  url={[Repository URL]}
}
```

---

## Appendix: Command Quick Reference

| Task              | Command                                                                                                                       |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Setup PyTorch env | `uv venv .venv_pt && source .venv_pt/bin/activate && uv pip install torch --index-url https://download.pytorch.org/whl/cu131` |
| Setup TF env      | `uv venv .venv_tf --python 3.10 && source .venv_tf/bin/activate && uv pip install tensorflow[and-cuda]==2.17.0`               |
| Run decomposition | `python Extractor_Decomposer/partition.py --model_path [PATH]`                                                                |
| Run mutation      | `python Recomposer/partition_mutation.py --input_dir [DIR] --mutation_policy semantic_aware`                                  |
| Start fuzzing     | `python fuzz_loop/main.py --backend [pt/tf] --mutation_dir [DIR]`                                                             |

---

_Document generated: 2026-03-17_  
_For technical support, contact: [maintainer@example.com]_
