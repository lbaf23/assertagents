# AssertAgent

## Download

### Datasets

- teco500 see https://github.com/ncsu-swat/chatassert

- [py500](https://huggingface.co/datasets/lbaf23/py500)

Put `py500.jsonl`, `teco500.jsonl`, `teco500.zip`, and `py500.zip` into dir `data`,

### jdt-language-server

- [jdt-language-server 0.57.0](https://download.eclipse.org/jdtls/milestones/0.57.0/)

Extract `jdt-language-server-0.57.0-202006172108.tar.gz` into `data/resources`.



## Install

### Install Java Env

- Install pkg

```bash
sudo apt update
sudo apt install openjdk-8-jdk
sudo apt install maven-3.8
```

```bash
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64  # set
export PATH=$JAVA_HOME/bin:$PATH
```

- Set repo data

```bash
cd data
unzip teco500.zip -d /tmp/work
```


### Install Python Env

- npm 9.2.0

```bash
sudo apt install nodejs npm
```

- pyright-langserver (pyright 1.1.406)

```bash
npm install -g pyright
```

```bash
pip install uv poetry
```


### Install

```bash
pip install -r requirements.txt
```


## Run

### Run AssertAgents

#### teco500

- Setup cached repos.

```bash
unzip data/teco500.zip -d /tmp/work1
```

- Install and Check
```bash
# Install
python check_install.py --repo_cache_dir /tmp/work1/teco500

# Check run
python check_run_test.py --repo_cache_dir /tmp/work1/teco500

# Check debug
python check_debug.py --repo_cache_dir /tmp/work1/teco500
```

- Extract callees and cache them (to speed up later running)
```bash
mkdir cache

python extract_calls_called_by.py \
--repo_cache_dir 'data/teco500' \
--jdtls_path 'data/resources/jdt-language-server' \
--workspace_dir './cache/teco500_jdt_cache'

python make_explore_msg.py \
--repo_cache_dir='/tmp/work1/teco500' \
--calls_cache_dir='./cache/teco500' \
--calls_msg_cache_dir='./cache/teco500_calls_msg'
```


- Serve LLM

```bash
CUDA_VISIBLE_DEVICES=0,1 \
vllm serve 'Qwen3-Coder-30B-A3B-Instruct' \
--dtype 'bfloat16' \
--tensor_parallel_size 2 \
--max_model_len 32768 \
--enable-prompt-tokens-details \
--enable-prefix-caching \
--enable-auto-tool-choice \
--tool-call-parser 'qwen3_coder' \
--api_key '123456' \
--host '0.0.0.0' \
--port 12000
```

- Start assertagent

```bash
python assertagent.py \
--run_name 'Qwen3-Coder-30B-A3B-Instruct_xxx' \
--dataset_name 'teco500' \
--repo_cache_dir '/tmp/work1/teco500' \
--debug_cache_dir '/tmp/work1/teco500_debug' \
--calls_extract_dir 'cache/teco500' \
--lang 'Java' \
--model_path 'Qwen3-Coder-30B-A3B-Instruct' \
--nums 10 \
--max_tries 10 \
--temperature 1.0 \
--generation_mode '' \
--start_index 0 \
--end_index 500 \
--debug_port 6001 \
--with_dynamic \
--with_explore_agent \
--api_key '123456' \
--base_url 'http://localhost:12000/v1'
```


#### py500

- Setup cached repos.

```bash
unzip data/py500.zip -d /tmp/pywork1
```

- Install and Check
```bash
# Install
python check_install_py.py --repo_cache_dir /tmp/pywork1/py500

# Check run
python check_run_test_py.py --repo_cache_dir /tmp/pywork1/py500

# Check debug
python check_debug_py.py --repo_cache_dir /tmp/pywork1/py500
```

- Extract callees and cache them (to speed up later running)
```bash
mkdir cache

python extract_calls_called_by.py \
--repo_cache_dir '/tmp/pywork1/py500'

python make_explore_msg_py.py \
--repo_cache_dir='/tmp/pywork1/py500' \
--calls_cache_dir='./cache/py500' \
--calls_msg_cache_dir='./cache/py500_calls_msg'
```


- Serve LLM

```bash
CUDA_VISIBLE_DEVICES=0,1 \
vllm serve 'Qwen3-Coder-30B-A3B-Instruct' \
--dtype 'bfloat16' \
--tensor_parallel_size 2 \
--max_model_len 32768 \
--enable-prompt-tokens-details \
--enable-prefix-caching \
--enable-auto-tool-choice \
--tool-call-parser 'qwen3_coder' \
--api_key '123456' \
--host '0.0.0.0' \
--port 12000
```

- Start assertagent

```bash
python assertagent.py \
--run_name 'Qwen3-Coder-30B-A3B-Instruct_xxx' \
--dataset_name 'py500' \
--repo_cache_dir '/tmp/pywork1/py500' \
--debug_cache_dir '/tmp/pywork1/py500_debug' \
--calls_extract_dir 'cache/py500' \
--lang 'Python' \
--model_path 'Qwen3-Coder-30B-A3B-Instruct' \
--nums 10 \
--max_tries 10 \
--temperature 1.0 \
--generation_mode '' \
--start_index 0 \
--end_index 500 \
--with_dynamic \
--with_explore_agent \
--api_key '123456' \
--base_url 'http://localhost:12000/v1'
```





### Run Directly Prompt

```bash
python directly_prompt.py \
--run_name 'Qwen3-Coder-30B-A3B-Instruct_xxx' \
--dataset_name 'teco500' \
--lang 'Java' \
--model_path 'Qwen3-Coder-30B-A3B-Instruct' \
--temperature 0.7 \
--top_p 0.8 \
--top_k 20 \
--generation_mode '' \
--api_key '123456' \
--base_url 'http://localhost:12000/v1'
```


## Evaluate

- Install codebleu

https://github.com/k4black/codebleu

- Evaluate

```bash
python evaluate.py \
--run_name 'Qwen3-Coder-30B-A3B-Instruct_xxx' \
--dataset_name 'teco500' \
--method 'assertagent' \
--lang 'Java' \
--result_type 'json'
```

- Evaluate run

```bash
python evaluate_run.py \
--run_name 'Qwen3-Coder-30B-A3B-Instruct_xxx' \
--repo_cache_dir '/tmp/work1/teco500' \
--dataset_name 'teco500' \
--method 'directly_prompt' \
--lang 'Java'
```

## Show results

```bash
python show_result.py \
--dataset_name 'teco500' \
--run_name_list 'Qwen3-coder-30B-A3B-Instruct_xxx' \
--method_list 'assertagent'
```
