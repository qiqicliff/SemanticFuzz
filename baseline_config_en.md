# SemanticFuzz Experimental Reproducibility Detailed Configuration Instructions (Response to Baseline Comparison Reproducibility Concerns)
## 1 Overview of Research and Baseline Methods
The SemanticFuzz proposed in this paper is an API-level fuzzing tool for deep learning frameworks. To ensure the fairness, reproducibility, and rigor of baseline comparisons, this experiment uniformly selects four mainstream SOTA API-level fuzzing tools as baseline comparators, including FreeFuzz, DeepREL, TitanFuzz, and DFuzz. All baseline methods strictly reuse the official open-source code without custom modifications or strategy fine-tuning, and are uniformly adapted to the experimental software and hardware environment and testing rules of this paper, thoroughly eliminating interference from experimental variables. In response to the reviewer's concerns regarding missing details such as baseline versions, commit records, prompts, model parameters, timeout strategies, hardware isolation, test case generation, crash classification, deduplication, and replay procedures, the following provides a complete and refined supplementary explanation.
## 2 Basic Runtime Environment Configuration (Unified for All Methods, Complete Hardware Isolation)
All configurations in this chapter apply globally to SemanticFuzz and the four baseline methods, ensuring that all comparative experiments are conducted in identical environments, achieving full-dimensional alignment in hardware, software, and basic parameters.
### 2.1 Hardware Environment
All experiments ran independently on a unified physical server, with dedicated and non-preemptible hardware resources, with the following specific configuration:
- **CPU**: AMD EPYC 7282, total memory 128G, dedicated resources throughout, no multitasking contention
- **GPU**: A single NVIDIA A800 GPU with 50GB dedicated memory; all methods are run on a single GPU with no multi-GPU scheduling differences
### 2.2 Software and Framework Versions
Fix the deep learning framework version, all baseline methods and the method in this paper are uniformly adapted, with no version compatibility differences:
- PyTorch version: v2.4.1
- TensorFlow version: v2.17.0
- Python runtime environment: Compatible with stable versions of various frameworks, globally unified base version of dependency libraries
### 2.3 General Fixed Hyperparameters (Unified for All Methods)
- **Random Seed**: Globally fix the random seed to 42, covering the entire process of framework initialization, test case generation, mutation sampling, and random selection, thoroughly fixing experimental randomness
- **LLM General Configuration**: All methods relying on large models uniformly adopt Qwen2.5-Coder-7B, with the model downloaded from the Hugging Face official repository and deployed locally, eliminating online invocation interference due to network fluctuations; the model's temperature parameter is set to 0, completely eliminating generation randomness to ensure reproducibility of results
- **Experimental Replication Mechanism**: All experimental groups independently repeated the experiments 5 times, conducting statistical analysis through multiple rounds of replication to calculate means and variances, enhancing the reliability of experimental results and avoiding random errors from single experiments
- **Maximum number of mutations**: Globally limit the number of mutations per test case to no more than 10, unified mutation termination condition
## 3 Baseline Method Version and Source Code Reproduction Specification
The four baseline methods selected in this study each have only one official release version, with no multi-branch iteration differences. The experiments strictly follow the official default configurations, fully reuse the original code, commit hashes, prompt strategies, and core parameters, without any custom modifications.
- **FreeFuzz**: Reuse the official open-source mainline version https://github.com/ise-uiuc/FreeFuzz.git, strictly adopt the repository's default configuration file, retain the native mutation strategies (value mutation, type mutation, database mutation all enabled), timeout threshold, and API traversal rules, with no parameter tuning
```sh
MongoDB database configuration.
[mongodb]
# your-mongodb-server
host = 127.0.0.1
# mongodb port
port = 27017 
# name of pytorch database
torch_database = freefuzz-torch
# name of tensorflow database
tf_database = freefuzz-tf
Output directory configuration.
[output]
# output directory for pytorch
torch_output = torch-output
# output directory for tensorflow
tf_output = tf-output
Oracle configuration.
[oracle]
# enable crash oracle
enable_crash = true
# enable cuda oracle
enable_cuda = true
# enable precision oracle
enable_precision = true
# float difference bound: if |a-b| > bound, a is different than b
float_difference_bound = 1e-5
# max time bound: if time(low_precision) > bound * time(high_precision),
# it will be considered as a potential bug
max_time_bound = 10
# only consider the call with time(call) > time_thresold
time_thresold = 1e-3
Mutation stratgy configuration.
[mutation]
enable_value_mutation = true
enable_type_mutation = true
enable_db_mutation = true
# the number of times each api is executed
each_api_run_times = 1000
```

- **DeepREL**: Use the official unique open-source version https://github.com/ise-uiuc/DeepREL.git, fully preserving its proprietary API relationship inference mechanism, seed selection logic, and test execution rules, adapted to the unified framework version and hardware environment in this paper
```sh
MongoDB database configuration.
[mongodb]
# your-mongodb-server
host = 127.0.0.1
# mongodb port
port = 27017 
# name of pytorch database
torch_database = torch
# name of tensorflow database
tf_database = tf
DeepREL configuration
[DeepREL]
test_number = 1000
top_k = 10
iteration = 10
```

- **TitanFuzz**: Uses the official open-source stable version https://github.com/ise-uiuc/TitanFuzz.git, retains the native LLM prompt engineering strategy, seed program generation and evolutionary mutation process, and uniformly adapts to the deployment method of the Qwen2.5-Coder-7B model in this paper
    -  64-core workstation with 256 GB RAM and running Ubuntu 20.04.5 LTS with 4 NVIDIA RTX A6000 GPUs. If you run on diferent GPUs and encountered OOM issues with the default generation batch size (30), you may consider setting a smaller batch size by changine the BATCH_SIZE=30

- **DFuzz**: Reproduced based on the official open-source version, fully preserving its fuzzing scheduling logic, test case generation, and anomaly detection rules```sh
{
    "api_keys": [
        ""
    ],
    "api_base": "https://api.openai.com/v1"
}

Step I: Context-Free Edge Case Extraction
Corresponding to the "edge_case_extraction" folder, used to extract edge cases from PyTorch source code.

Step II: Get API Description
Corresponding to the "get_api_reference" folder, used to generate the description for the target APIs.

Step III: Edge Case-Based Mutation
Corresponding to the "gen_program" folder, used to generate initial programs and perform edge case-based mutation.
```

All non-method-specific configurations of baseline methods (hardware, framework version, random seed, LLM model, retry mechanism, etc.) are exactly the same as SemanticFuzz, retaining only the native core algorithms and strategy differences of each method to ensure the uniqueness of variables in comparative experiments.
## 4 Test Budget and Timeout Execution Strategy (Refined Unified Rule)
For the operational characteristics of different types of baseline methods, set differentiated and fixed time budgets, with all rules globally transparent and reproducible:
### 4.1 Global API Test Budget
The budget for each method single API test is fixed at 600s, with strict upper limit control on single API test duration to eliminate result bias caused by inconsistent durations.
### 4.2 Global Maximum Runtime
- **Non-LLM baseline methods**: Higher runtime efficiency, set global default maximum runtime to 8h
- **LLM-based baseline methods (including SemanticFuzz, TitanFuzz, etc.)**: Model inference takes longer, set global default maximum runtime to 20h
## 5 API Filtering and Filtering Rules (Unified Filtering Criteria)
To unify the test API scope for all methods, avoid interference from invalid APIs, and establish standardized API filtering rules, applicable to all methods:
### 5.1 Valid API Definition
An API that can normally obtain official API documentation, support semantic parsing and semantic decomposition, and complete semantic extraction and seed generation is deemed as a usable and valid API.
### 5.2 Filter and Remove Rules
- Filter out all APIs that have been officially deprecated by the framework and marked as deprecated
- Exclude APIs that cannot be adapted to single test files or cannot be compiled and run independently
- Temporarily deprecate timeouts and occasional crashes APIs not caused by algorithm design flaws to improve overall testing efficiency, while recording details of all removed APIs to ensure experiment traceability
### 5.3 Test API Total
This experiment covers 1992 effective APIs of PyTorch (v2.4.1) and 4003 effective APIs of TensorFlow (v2.17.0), and all comparison methods are tested on exactly the same set of APIs.
## 6 Failure-handling Rules
All baseline methods and the method in this paper adopt completely unified anomaly handling, retry, and invalid case determination rules, standardizing crash classification and filtering logic:
### 6.1 Invalid Use Case Determination and Discard Rules
Test programs falling into any of the following three categories are directly marked as invalid cases, discarded, excluded from valid result statistics, and not regenerated: code compilation failure, program crash during execution, execution time exceeding the single API 600s timeout limit.
### 6.2 Automatic Retry Mechanism
For non-programmatic accidental anomalies, initiate a fixed retry strategy: when temporary API call errors or brief network failures occur, retain the original test seed and automatically trigger a retry, with a maximum of 2 retry attempts; if the test still fails after 2 consecutive retries, directly abandon the test case and terminate the testing process for the current seed.
### 6.3 Failure Record and Statistical Criteria
All failures, timeouts, and retry exceptions are categorized and logged as error logs, with detailed distinctions made between types such as compilation errors, runtime crashes, timeout exceptions, API call exceptions, and network failures; all exception cases are excluded from the count of valid executions and final experiment metrics, ensuring consistency in metric statistical criteria.
## 7 Test Case Deduplication and Replay Process
### 7.1 Deduplication criteria
Using "API call path + core parameter combination + code semantic structure" as the deduplication criterion, remove duplicate test cases that are completely homogeneous and lack variation differences, avoiding redundant statistics of invalid samples and ensuring the accuracy of effective case statistics.
### 7.2 Result Replay Process
All experimental results support full replay: fix the global seed, replicate the software and hardware environment, reuse consistent timeout and retry rules, preserve the original prompts and model parameters; five repeated experiments each retain log files, test case files, and anomaly records, allowing anytime reproduction of single-round and multi-round experimental results, ensuring the authenticity and reliability of comparative results.
## 8 LLM ablation experiment selection criteria
This paper conducts ablation experiments on multiple mainstream open-source LLMs during the model selection phase. Under identical software and hardware environments, test budgets, API ranges, and exception handling rules, the semantic decomposition, seed generation, and semantic boundary mutation capabilities of different models are compared. Ultimately, Qwen2.5-Coder-7B, which demonstrates the best overall performance, is selected as the fixed model and used throughout the code generation and semantic parsing processes for both the proposed method and baseline methods, ensuring consistency in the model variable.
## 9 Reproducibility Summary
All baseline comparison experiments in this paper implement **full-dimensional configuration uniformity, rule transparency, and process traceability**: dedicated hardware resource isolation, fixed software versions, globally unified random seeds, differentiated fixed time budgets, standardized failure and retry rules, consistent API filtering criteria, unified model parameters and prompt strategies, and all baseline methods reuse official default configurations without custom modifications. The above complete configuration fully supports the reproducibility of experimental results, effectively addressing issues of missing baseline comparison details and insufficient result persuasiveness.
