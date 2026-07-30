# SemanticFuzz

# Install uv (if not installed)pip install uv

# Create and activate virtual environment uv venv --python 3.10
uv activate

# Install PyTorch GPU version (CUDA 13.1)# uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu131
uv pip install torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0  -i https://pypi.tuna.tsinghua.edu.cn/simple

# Verify installationpython -c "import torch; print('PyTorch版本:', torch.__version__); print('CUDA:', torch.cuda.is_available())"
cd target directorysource .venv/bin/activate

python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available())"
PyTorch: 2.4.1+cu124
CUDA: True


  uv venv --python 3.10
source .venv/bin/activate
uv pip install tensorflow[and-cuda]==2.17.0 -i https://pypi.tuna.tsinghua.edu.cn/simple